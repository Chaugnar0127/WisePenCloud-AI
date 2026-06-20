import uuid
from typing import List
from datetime import datetime, timezone

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from chat.domain.entities import ResourceAttachmentRef, TemporaryAttachmentRef
from chat.domain.repositories import SessionRepository
from chat.service_client import FileStorageClient, ResourceClient
from common.core.domain import R
from common.logger import info, warning
from common.security import SecurityContextHolder, require_login

from chat.api.schemas.attachment import (
    AddResourceAttachmentsRequest,
    DeleteAttachmentRequest,
    InitUploadRequest,
    InitUploadResponse,
)
from chat.container import Container

router = APIRouter(tags=["attachment"])


@router.post("/initUploadTemporaryAttachment", response_model=R[InitUploadResponse])
@inject
async def init_temp_attachment_upload(
    req: InitUploadRequest,
    user_id: str = Depends(require_login),
    session_repo: SessionRepository = Depends(Provide[Container.session_repo]),
    file_storage_client: FileStorageClient = Depends(Provide[Container.file_storage_client])
):
    biz_path = f"{user_id}/{req.session_id}"

    init_upload_res = await file_storage_client.init_upload(
        md5=req.md5,
        extension=req.extension,
        scene="PRIVATE_AI_ATTACHMENT",
        biz_path=biz_path,
        config_id=None,
        expected_size=req.file_size,
    )

    session = await session_repo.get_session_for_user(req.session_id, user_id)
    # 构建 attachment_id
    attachment_id = uuid.uuid4().hex

    ref = TemporaryAttachmentRef(
        attachment_id=attachment_id, attachment_name=req.filename,
        object_key=init_upload_res.object_key,
        extension=req.extension,
        file_size=req.file_size,
        mime_type=None,
    )
    session.temporary_attachment_refs.append(ref)
    session.updated_at = datetime.now(timezone.utc)
    await session.save()

    info("temporary attachment upload initialized", user_id=user_id)

    return R.success(data=InitUploadResponse(
        attachment_id=attachment_id,
        object_key=init_upload_res.object_key,
        put_url=init_upload_res.put_url,
        callback_header=init_upload_res.callback_header,
    ))


@router.post("/addResourceAttachments", response_model=R[List[str]], status_code=200)
@inject
async def add_resource_attachments(
    req: AddResourceAttachmentsRequest,
    user_id: str = Depends(require_login),
    session_repo: SessionRepository = Depends(Provide[Container.session_repo]),
    resource_client: ResourceClient = Depends(Provide[Container.resource_client]),
):
    session = await session_repo.get_session_for_user(req.session_id, user_id)
    attachment_ids = []

    for resource_id in req.resource_ids:
        resource_info = await resource_client.get_resource_info(
            resource_id=resource_id,
            user_id=user_id,
            group_role_map=SecurityContextHolder.get_group_role_map(),
        )
        resource_type = resource_info.resource_type
        attachment_name = resource_info.resource_name

        # 已存在记录
        existing = next((ref for ref in session.resource_attachment_refs if ref.resource_id == resource_id), None)
        if existing is not None:
            existing.resource_type = resource_type
            existing.attachment_name = attachment_name
            existing.deleted = False
            attachment_ids.append(existing.attachment_id)
            continue

        # 构建 attachment_id
        attachment_id = uuid.uuid4().hex

        session.resource_attachment_refs.append(
            ResourceAttachmentRef(
                attachment_id=attachment_id,
                attachment_name=attachment_name,
                resource_id=resource_id,
                resource_type=resource_type,
            )
        )
        attachment_ids.append(attachment_id)

    session.updated_at = datetime.now(timezone.utc)
    await session.save()

    info("resource attachments added", user_id=user_id, count=len(req.resource_ids))
    return R.success(data=attachment_ids)


@router.post("/deleteAttachment", response_model=R)
@inject
async def delete_attachment(
    req: DeleteAttachmentRequest,
    user_id: str = Depends(require_login),
    session_repo: SessionRepository = Depends(Provide[Container.session_repo]),
    file_storage_client: FileStorageClient = Depends(Provide[Container.file_storage_client])
):
    session = await session_repo.get_session_for_user(req.session_id, user_id)
    matched_temporary_attachment_ref = next((a for a in session.temporary_attachment_refs if a.attachment_id == req.attachment_id and not a.deleted), None)
    matched_resource_attachment_ref = next((a for a in session.resource_attachment_refs if a.attachment_id == req.attachment_id and not a.deleted), None)

    if matched_temporary_attachment_ref is None and matched_resource_attachment_ref is None:
        warning("attachment delete skipped", user_id=user_id, attachment_id=req.attachment_id)
        return R.success()

    if matched_temporary_attachment_ref is not None:
        matched_temporary_attachment_ref.deleted = True
        await file_storage_client.delete_file(matched_temporary_attachment_ref.object_key)

    if matched_resource_attachment_ref is not None:
        matched_resource_attachment_ref.deleted = True

    session.updated_at = datetime.now(timezone.utc)
    await session.save()

    info("attachment delete succeeded", user_id=user_id, attachment_id=req.attachment_id)
    return R.success()
