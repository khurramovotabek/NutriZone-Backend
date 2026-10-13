"""
Chat HTTP API views.

Thin per Django Implementation Blueprint §3. No view instantiates a
repository/selector directly outside `composition.py`, imports
`infrastructure.models`, or constructs a Domain aggregate.

**Every Conversation-lifecycle mutation endpoint returns an honest
HTTP 501** -- the direct, disclosed consequence of this phase's own
Step 1 re-verification: zero Application Services exist for Chat.
`Message`-lifecycle mutations (send/edit/delete/delivered/read) are
deliberately NOT duplicated here as HTTP endpoints -- they are
exposed only over the WebSocket protocol (`consumers.py`), avoiding
building the same unsupported capability twice under two different
transports. Every 501 response states precisely which capability is
missing, matching the identical pattern already established by
Reviews' Phase 3.

**No `list_unassigned` (operator queue) endpoint exists**, disclosed
here rather than silently omitted: `ConversationRepository.
list_unassigned` exists, but no corresponding `ConversationSelector`
method does, and using the heavier aggregate-reconstructing
repository for what should be a lightweight list view would break
the established "selectors for reads, repositories for reads-that-
need-full-aggregate-reconstruction" convention followed by every
prior module.
"""
from __future__ import annotations

import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from apps.chat.domain.enums import AttachmentType, ConversationType, MessageType, ParticipantRole
from apps.chat.infrastructure import composition, presence
from apps.chat.interfaces.api.v1.filters import parse_conversation_list_params, parse_pagination_only
from apps.chat.interfaces.api.v1.pagination import ChatPagination
from apps.chat.interfaces.api.v1.permissions import (
    CanOpenStoreConversation,
    ManageConversation,
    ViewOwnConversations,
    ViewStatistics,
)
from apps.chat.interfaces.api.v1.permissions import (
    SendMessage as SendMessagePermission,
)
from apps.chat.interfaces.api.v1.serializers import (
    AddParticipantSerializer,
    AssignOperatorSerializer,
    OpenConversationSerializer,
    SendMessageSerializer,
)
from common.exceptions import PermissionDenied, ResourceNotFound, ValidationFailed
from common.responses import paginated_response, success_response
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _attach_identity(request) -> None:
    request.identity = request.user


def _actor_id(request):
    return getattr(getattr(request, "user", None), "id", None)


def _message_payload(message) -> dict:
    """The wire shape of a message -- shared with the dashboard (apps/chat/infrastructure/realtime.py)."""
    from apps.chat.infrastructure.realtime import message_payload

    return message_payload(message)


_MISSING_APPLICATION_SERVICE = "This operation requires an Application Service that is not yet implemented. Zero Application Services currently exist for the Chat module; orchestrating this transition (load -> mutate -> persist -> stage event) cannot be done safely from the Interfaces layer without one."


def _load_conversation_or_404(conversation_id: str):
    conversation = composition.build_conversation_repository().get_by_id(uuid.UUID(conversation_id))
    if conversation is None:
        raise ResourceNotFound("Conversation not found.")
    return conversation


def _assert_active_participant_or_403(conversation, user_id) -> None:
    """Object-level authorization -- the DRF permission class only checks the generic `chat.conversation.view_own` code; whether THIS user is actually a participant of THIS specific conversation is a per-object check that must happen here, against the loaded aggregate itself, not duplicated as a second parallel mechanism (see permissions.py's own module docstring)."""
    participant = next((p for p in conversation.participants.values() if p.user_id == user_id and p.is_active), None)
    if participant is None:
        raise PermissionDenied("You are not an active participant of this conversation.")


class ChatThrottle(ScopedRateLimitThrottle):
    scope = "chat.operation"
    limit = 3000
    window_seconds = 3600
    identifier_source = "user"


def _conversation_card_payload(row: dict) -> dict:
    return {
        "id": row["id"], "conversation_type": row["conversation_type"], "status": row["status"],
        "assigned_operator_id": row.get("assigned_operator_id"), "last_activity_at": row.get("last_activity_at"),
        "other_participant_id": row.get("other_participant_id"), "other_participant_is_online": row.get("other_participant_is_online", False),
        "other_participant_full_name": row.get("other_participant_full_name"), "other_participant_avatar_url": row.get("other_participant_avatar_url"),
        "store": row.get("store"),
        "unread_count": row.get("unread_count", 0), "last_message": row.get("last_message"),
    }


def _assert_card_allowed(conversation, content: str | None) -> None:
    """An order card may only show an order that belongs to someone in this conversation (never another customer's order)."""
    from apps.chat.domain.value_objects import CARD_REF

    if not content or not CARD_REF.match(content) or not content.startswith("order:"):
        return
    from apps.ordering.infrastructure.models import OrderModel

    owner = OrderModel.objects.filter(pk=content.split(":", 1)[1]).values_list("customer_id", flat=True).first()
    members = {p.user_id for p in conversation.participants.values() if p.is_active}
    if owner is None or owner not in members:
        raise PermissionDenied("This order cannot be shared in this conversation.")


def _support_extras(conversation, viewer_id) -> dict:
    """Support chats: working hours and the customer's 1–5 ★ rating (asked once the chat is closed)."""
    if conversation.conversation_type.value != "customer_support":
        return {}
    from apps.chat.infrastructure import automation
    from apps.chat.infrastructure.models import ConversationRating

    cfg = automation.chat_settings()
    rating = ConversationRating.objects.filter(conversation_id=conversation.id).order_by("-created_at").values("score", "comment").first()
    is_customer = any(p.user_id == viewer_id and p.role.value == "customer" for p in conversation.participants.values())
    return {
        "support_hours": {"open": automation.is_open(cfg=cfg), "label": automation.hours_label(cfg)},
        "rating": rating,
        "can_rate": bool(cfg.rating_enabled and is_customer and automation.can_rate(conversation.id, conversation.status.value)),
    }


def _conversation_detail_payload(conversation, viewer_id: uuid.UUID | None = None) -> dict:
    from apps.chat.infrastructure.selectors import _identity_summaries, _store_summaries

    other_participant = next((p for p in conversation.participants.values() if p.is_active and p.user_id != viewer_id), None) if viewer_id else None
    other_identity = _identity_summaries([other_participant.user_id]).get(other_participant.user_id) if other_participant else None
    store = _store_summaries([conversation.store_id]).get(conversation.store_id) if conversation.store_id else None

    return {
        "id": str(conversation.id), "conversation_type": conversation.conversation_type.value, "status": conversation.status.value,
        "assigned_operator_id": str(conversation.assigned_operator_id) if conversation.assigned_operator_id else None,
        "last_activity_at": conversation.last_activity_at.isoformat() if conversation.last_activity_at else None,
        "other_participant_full_name": other_identity["full_name"] if other_identity else None,
        "other_participant_avatar_url": other_identity["avatar_url"] if other_identity else None,
        "store": store,
        "participants": [
            {
                "id": str(p.id), "user_id": str(p.user_id), "role": p.role.value, "joined_at": p.joined_at.isoformat(),
                "removed_at": p.removed_at.isoformat() if p.removed_at else None, "is_online": presence.is_online(p.user_id) if p.is_active else False,
            }
            for p in conversation.participants.values()
        ],
        **_support_extras(conversation, viewer_id),
    }


# ============================================================
# Conversations -- read (real) and mutation (honest 501) endpoints
# ============================================================


class ConversationListCreateView(APIView):
    """GET is real (backed by `ConversationSelector.list_for_user`, scoped to the requesting user's own conversations). POST (open) is an honest 501."""

    throttle_classes = [ChatThrottle]
    permission_classes = [ViewOwnConversations]

    @extend_schema(tags=["Chat"], summary="List the authenticated user's conversations", description="Supports filter[status]. Backed by ConversationSelector.list_for_user.", responses={200: OpenApiResponse(description="Conversation collection"), **_responses(401, 403, 422)})
    def get(self, request):
        _attach_identity(request)
        params = parse_conversation_list_params(request.query_params)
        pagination = ChatPagination.from_query_params(request.query_params)
        rows, total = composition.build_conversation_selector().list_for_user(user_id=request.user.id, status=params.status, page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_conversation_card_payload(r) for r in rows], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Chat"], summary="Open a new conversation", request=OpenConversationSerializer, responses={201: OpenApiResponse(description="Conversation opened"), **_responses(401, 403, 422)})
    def post(self, request):
        """
        Phase 03B: closes the Open Conversation gap, the second real
        Application Service for Chat, following the exact pattern
        `SendMessage` established. `opened_by` comes strictly from
        `request.user.id` -- never a client-supplied value, matching
        this phase's own explicit security rule.
        """
        _attach_identity(request)
        serializer = OpenConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["conversation_type"] == ConversationType.CUSTOMER_SUPPORT.value:
            # One support chat per customer (NutriZone support, online orders -- not a branch): resume the open one
            # instead of starting a new thread every time.
            from apps.chat.infrastructure.models import ConversationModel, ParticipantModel

            mine = ParticipantModel.objects.filter(user_id=request.user.id, role=ParticipantRole.CUSTOMER.value, removed_at__isnull=True).values("conversation_id")
            existing = ConversationModel.objects.filter(id__in=mine, conversation_type=ConversationType.CUSTOMER_SUPPORT.value).exclude(status="archived").order_by("-last_activity_at").first()
            if existing is not None:
                resumed = composition.build_conversation_repository().get_by_id(existing.id)
                return success_response(data=_conversation_detail_payload(resumed, viewer_id=request.user.id), status_code=200)

        conversation = composition.build_open_conversation(_actor_id(request)).execute(
            opened_by=request.user.id, conversation_type=ConversationType(data["conversation_type"]), opener_role=ParticipantRole(data["opener_role"]),
        )
        return success_response(data=_conversation_detail_payload(conversation, viewer_id=request.user.id), status_code=201)


class ConversationDetailView(APIView):
    permission_classes = [ViewOwnConversations]

    @extend_schema(tags=["Chat"], summary="Get a conversation by id", responses={200: OpenApiResponse(description="Conversation detail"), **_responses(401, 403, 404)})
    def get(self, request, conversation_id: str):
        _attach_identity(request)
        conversation = _load_conversation_or_404(conversation_id)
        _assert_active_participant_or_403(conversation, request.user.id)
        return success_response(data=_conversation_detail_payload(conversation, viewer_id=request.user.id))


class ConversationMessageListView(APIView):
    def get_permissions(self):
        return [SendMessagePermission()] if self.request.method == "POST" else [ViewOwnConversations()]

    @extend_schema(tags=["Chat"], summary="List a conversation's messages", description="Backed by MessageSelector.list_for_conversation -- no filter beyond pagination, since that selector accepts none.", responses={200: OpenApiResponse(description="Message collection"), **_responses(401, 403, 404)})
    def get(self, request, conversation_id: str):
        _attach_identity(request)
        conversation = _load_conversation_or_404(conversation_id)
        _assert_active_participant_or_403(conversation, request.user.id)
        page, page_size = parse_pagination_only(request.query_params)
        rows, total = composition.build_message_selector().list_for_conversation(uuid.UUID(conversation_id), page, page_size)
        total_pages = max((total + page_size - 1) // page_size, 1)
        return paginated_response(data=rows, pagination={"strategy": "page", "page": page, "page_size": page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Chat"], summary="Send a message to a conversation", request=SendMessageSerializer, responses={201: OpenApiResponse(description="Message sent"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, conversation_id: str):
        """
        Phase 03B: closes the top-priority Chat gap named by this
        phase's own charter. Reuses the exact same ownership check
        already proven safe for the read side of this same view
        (`_assert_active_participant_or_403`) -- not duplicated, not
        redesigned. The sender comes strictly from `request.user.id`;
        no client-supplied sender identity is ever trusted, matching
        this phase's own explicit security rule.
        """
        _attach_identity(request)
        conversation = _load_conversation_or_404(conversation_id)
        _assert_active_participant_or_403(conversation, request.user.id)

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        attachment = None
        if data.get("attachment_url"):
            from apps.chat.domain.value_objects import AttachmentMetadata

            # Real, closed gap: `attachment_url` was a plain `URLField`
            # -- any client-supplied URL, verified against nothing. A
            # message can only ever attach a URL this deployment's own
            # media pipeline actually produced (see
            # ConversationAttachmentUploadView below), never an
            # arbitrary external one.
            if not composition.build_media_storage_gateway().confirm_media_url_exists(data["attachment_url"]):
                raise ValidationFailed("attachment_url does not reference an uploaded file.", details={"fields": [{"field": "attachment_url", "code": "NOT_FOUND"}]})

            # Real, pre-existing bug this phase's own first end-to-end
            # attachment test caught: `ChoiceField.validated_data`
            # yields the raw string ("image"), never an `AttachmentType`
            # member -- `AttachmentMetadata` (a typed dataclass with no
            # coercion of its own) stored that raw string, then crashed
            # with a 500 the moment `DjangoMessageRepository.save()`
            # tried `.value` on it. Cast explicitly, exactly like
            # `MessageType(data["message_type"])` two lines below
            # already does for the same reason.
            attachment = AttachmentMetadata(
                attachment_type=AttachmentType(data["attachment_type"]), url=data["attachment_url"],
                filename=data["attachment_filename"], size_bytes=data["attachment_size_bytes"],
            )

        if data["message_type"] == MessageType.CARD.value:
            _assert_card_allowed(conversation, data.get("content"))

        # A customer writing again into their (reused) support chat after it was closed opens it again -- a new question.
        if conversation.conversation_type.value == "customer_support" and conversation.status.value == "closed" and any(
                p.user_id == request.user.id and p.role.value == "customer" for p in conversation.participants.values()):
            conversation = composition.build_reopen_conversation(_actor_id(request)).execute(conversation_id=conversation.id)

        message = composition.build_send_message(_actor_id(request)).execute(
            conversation_id=uuid.UUID(conversation_id), sender_id=request.user.id, message_type=MessageType(data["message_type"]),
            content=data.get("content"), attachment=attachment, reply_to_message_id=data.get("reply_to_message_id"),
        )
        payload = _message_payload(message)

        # Push it live: the open thread gets the message, every other active participant's inbox a refresh pointer
        # (shared with the dashboard's Chat markazi, see apps/chat/infrastructure/realtime.py).
        from apps.chat.infrastructure.realtime import push_message

        push_message(conversation_id, payload, request.user.id, [p.user_id for p in conversation.participants.values() if p.is_active])

        return success_response(data=payload, status_code=201)


class OpenStoreConversationView(APIView):
    """
    `POST /chat/conversations/store/<store_id>` -- the one, safe,
    customer-initiated exception to staff-only participant management
    (see `OpenStoreConversation`'s own docstring). Deliberately its
    own endpoint, not a variant of `ConversationListCreateView.post`
    (which stays exactly what it was: a plain, opener-only-participant
    open) -- this one's whole job is atomically opening a conversation
    *and* seating the store's owner in it, a materially different,
    store-scoped operation.
    """

    throttle_classes = [ChatThrottle]
    permission_classes = [CanOpenStoreConversation]

    @extend_schema(tags=["Chat"], summary="Open (or resume) a sales conversation with a store's owner", responses={201: OpenApiResponse(description="Conversation opened or resumed"), **_responses(401, 403, 404, 422)})
    def post(self, request, store_id: str):
        from django.shortcuts import get_object_or_404

        from apps.stores.infrastructure.models import Store, StoreStatus

        _attach_identity(request)
        try:
            store_uuid = uuid.UUID(store_id)
        except ValueError:
            raise ResourceNotFound("Store not found.") from None
        # Same visibility rule the customer-facing store detail page already uses (apps/stores/interfaces/api/v1/views.py) -- never a stricter or looser one invented here.
        store = get_object_or_404(Store.objects.exclude(status=StoreStatus.INACTIVE).filter(kind="store"), id=store_uuid)

        if store.owner_id == request.user.id:
            raise ValidationFailed("You cannot open a sales conversation with your own store.", details={"fields": [{"field": "store_id", "code": "INVALID"}]})

        conversation = composition.build_open_store_conversation(_actor_id(request)).execute(customer_id=request.user.id, store_owner_id=store.owner_id, store_id=store.id)
        return success_response(data=_conversation_detail_payload(conversation, viewer_id=request.user.id), status_code=201)


class CustomerProfileView(APIView):
    """
    `GET /chat/conversations/<id>/customer-profile` -- the store
    manager's own popover: the customer's avatar/full name/phone
    number/Telegram username plus their recent order history. Real,
    closed gap this module's own read-shape previously disclosed
    explicitly (see `ConversationSelector`'s pre-fix state): "no
    customer name, avatar, order history... exist anywhere in the
    Chat API's response shapes."

    Deliberately restricted to the requester's own OPERATOR
    participation in THIS conversation -- never a store-wide "look up
    any customer" capability, and never usable by the customer to pull
    their own profile through this route (that already exists at
    `GET /identity/users/me`).
    """

    permission_classes = [ViewOwnConversations]

    @extend_schema(tags=["Chat"], summary="Get the customer's profile for a conversation (operator-only)", responses={200: OpenApiResponse(description="Customer profile plus recent orders"), **_responses(401, 403, 404)})
    def get(self, request, conversation_id: str):
        _attach_identity(request)
        conversation = _load_conversation_or_404(conversation_id)
        _assert_active_participant_or_403(conversation, request.user.id)

        requester = next((p for p in conversation.participants.values() if p.is_active and p.user_id == request.user.id), None)
        if requester is None or requester.role != ParticipantRole.OPERATOR:
            raise PermissionDenied("Only the store operator side of a conversation can view the customer's profile.")

        customer = next((p for p in conversation.participants.values() if p.is_active and p.role == ParticipantRole.CUSTOMER), None)
        if customer is None:
            raise ResourceNotFound("This conversation has no active customer participant.")

        profile = composition.build_customer_profile_selector().get(customer.user_id)
        if profile is None:
            raise ResourceNotFound("Customer not found.")
        return success_response(data=profile)


class ConversationAttachmentUploadView(APIView):
    """
    `POST /chat/conversations/<id>/attachments` -- resolves a real,
    served URL for an image/video via the exact same media pipeline
    every other upload in this codebase already uses
    (`build_media_pipeline`, see `MyStoreMediaView` in
    apps/stores/interfaces/api/v1/views.py for the identical pattern).
    Returns the URL only; the caller still makes the existing, real
    `POST .../messages` call with it -- no new Message-creation path,
    no new storage model.
    """

    throttle_classes = [ChatThrottle]
    permission_classes = [SendMessagePermission]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(tags=["Chat"], summary="Upload an image/video attachment for a chat message", responses={201: OpenApiResponse(description="Attachment uploaded"), **_responses(401, 403, 404, 422)})
    def post(self, request, conversation_id: str):
        from apps.products.infrastructure.composition import build_media_pipeline
        from core.media import MediaType, MediaUploadRequest

        _attach_identity(request)
        conversation = _load_conversation_or_404(conversation_id)
        _assert_active_participant_or_403(conversation, request.user.id)

        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationFailed("No file was uploaded under the 'file' field.", details={"fields": [{"field": "file", "code": "REQUIRED"}]})

        is_video = bool(uploaded.content_type and uploaded.content_type.startswith("video/"))
        media_type = MediaType.VIDEO if is_video else MediaType.IMAGE
        result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, media_type=media_type))
        if result.is_failure:
            raise ValidationFailed(result.errors[0].message)
        processed = result.value

        from django.conf import settings as django_settings

        base = (getattr(django_settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
        url = f"{base}{django_settings.MEDIA_URL}{processed.storage_path}"
        return success_response(
            data={"attachment_type": "video" if is_video else "image", "attachment_url": url, "attachment_filename": uploaded.name, "attachment_size_bytes": uploaded.size},
            status_code=201,
        )


class ConversationRatingView(APIView):
    """`POST /chat/conversations/<id>/rating` {score 1–5, comment?} -- the customer rates a closed support chat, once."""

    throttle_classes = [ChatThrottle]
    permission_classes = [ViewOwnConversations]

    @extend_schema(tags=["Chat"], summary="Rate a closed support conversation (1–5 stars)", responses={201: OpenApiResponse(description="Rated"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, conversation_id: str):
        from apps.chat.infrastructure.automation import rate

        _attach_identity(request)
        try:
            conv_id = uuid.UUID(conversation_id)
        except ValueError as exc:
            raise ResourceNotFound("Conversation not found.") from exc
        score = request.data.get("score")
        rating = rate(conv_id, request.user.id, int(score) if str(score).isdigit() else 0, str(request.data.get("comment") or ""))
        return success_response(data={"score": rating.score, "comment": rating.comment}, status_code=201)


class AddParticipantView(APIView):
    throttle_classes = [ChatThrottle]
    permission_classes = [ManageConversation]

    @extend_schema(tags=["Chat Admin"], summary="Add a participant to a conversation", request=AddParticipantSerializer, responses={201: OpenApiResponse(description="Participant added"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, conversation_id: str):
        """
        Phase 03B: closes the Add Participant gap, the third real
        Application Service for Chat. Role validation and duplicate-
        participant rejection both already existed inside
        `Conversation.add_participant()` -- reused, not duplicated.
        """
        _attach_identity(request)
        serializer = AddParticipantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _load_conversation_or_404(conversation_id)  # existence check preserved, matching this endpoint's own pre-existing behavior
        data = serializer.validated_data

        conversation = composition.build_add_participant(_actor_id(request)).execute(
            conversation_id=uuid.UUID(conversation_id), user_id=data["user_id"], role=ParticipantRole(data["role"]),
        )
        return success_response(data=_conversation_detail_payload(conversation), status_code=201)


class RemoveParticipantView(APIView):
    throttle_classes = [ChatThrottle]
    permission_classes = [ManageConversation]

    @extend_schema(tags=["Chat Admin"], summary="Remove a participant from a conversation", responses={200: OpenApiResponse(description="Participant removed"), **_responses(401, 403, 404, 422)})
    def delete(self, request, conversation_id: str, user_id: str):
        _attach_identity(request)
        _load_conversation_or_404(conversation_id)
        conversation = composition.build_remove_participant(_actor_id(request)).execute(conversation_id=uuid.UUID(conversation_id), user_id=uuid.UUID(user_id))
        return success_response(data=_conversation_detail_payload(conversation))


class AssignOperatorView(APIView):
    throttle_classes = [ChatThrottle]
    permission_classes = [ManageConversation]

    @extend_schema(tags=["Chat Admin"], summary="Assign/reassign an operator", request=AssignOperatorSerializer, responses={200: OpenApiResponse(description="Operator assigned"), **_responses(401, 403, 404, 422)})
    def post(self, request, conversation_id: str):
        _attach_identity(request)
        serializer = AssignOperatorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _load_conversation_or_404(conversation_id)
        conversation = composition.build_assign_operator(_actor_id(request)).execute(conversation_id=uuid.UUID(conversation_id), operator_user_id=serializer.validated_data["operator_user_id"])
        return success_response(data=_conversation_detail_payload(conversation))


class CloseConversationView(APIView):
    throttle_classes = [ChatThrottle]
    permission_classes = [ManageConversation]

    @extend_schema(tags=["Chat Admin"], summary="Close a conversation", responses={200: OpenApiResponse(description="Conversation closed"), **_responses(401, 403, 404, 409)})
    def post(self, request, conversation_id: str):
        _attach_identity(request)
        _load_conversation_or_404(conversation_id)
        conversation = composition.build_close_conversation(_actor_id(request)).execute(conversation_id=uuid.UUID(conversation_id))
        return success_response(data=_conversation_detail_payload(conversation))


class ReopenConversationView(APIView):
    throttle_classes = [ChatThrottle]
    permission_classes = [ManageConversation]

    @extend_schema(tags=["Chat Admin"], summary="Reopen a closed conversation", responses={200: OpenApiResponse(description="Conversation reopened"), **_responses(401, 403, 404, 409)})
    def post(self, request, conversation_id: str):
        _attach_identity(request)
        _load_conversation_or_404(conversation_id)
        conversation = composition.build_reopen_conversation(_actor_id(request)).execute(conversation_id=uuid.UUID(conversation_id))
        return success_response(data=_conversation_detail_payload(conversation))


class ArchiveConversationView(APIView):
    throttle_classes = [ChatThrottle]
    permission_classes = [ManageConversation]

    @extend_schema(tags=["Chat Admin"], summary="Archive a conversation", responses={200: OpenApiResponse(description="Conversation archived"), **_responses(401, 403, 404, 409)})
    def post(self, request, conversation_id: str):
        _attach_identity(request)
        _load_conversation_or_404(conversation_id)
        conversation = composition.build_archive_conversation(_actor_id(request)).execute(conversation_id=uuid.UUID(conversation_id))
        return success_response(data=_conversation_detail_payload(conversation))


class UnreadCountView(APIView):
    """`GET /chat/unread-count` -- unread messages for the header / account menu badges."""

    permission_classes = [ViewOwnConversations]

    def get(self, request):
        from apps.chat.infrastructure.selectors import unread_total

        _attach_identity(request)
        return success_response(data=unread_total(request.user.id))


class ChatStatisticsView(APIView):
    permission_classes = [ViewStatistics]

    @extend_schema(tags=["Chat Admin"], summary="Chat statistics (conversation counts by status)", responses={200: OpenApiResponse(description="Statistics"), **_responses(401, 403)})
    def get(self, request):
        _attach_identity(request)
        selector = composition.build_chat_statistics_selector()
        return success_response(data={"conversation_counts_by_status": selector.conversation_counts_by_status()})
