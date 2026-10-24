from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from chat.domain.error_codes import ChatErrorCode
from common.core.domain import R, ResultCode
from common.core.exceptions import ServiceException
from common.logger import warn
from common.security.exceptions import PermissionException


class AdminRoute(APIRoute):
    """管理员响应保留真实错误码，失败路径不输出请求体或底层异常。"""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def safe_handler(request: Request) -> Response:
            request.state.admin_request_id = uuid4().hex
            try:
                return await handler(request)
            except RequestValidationError:
                status, code, message = 400, ResultCode.PARAM_ERROR.code, ResultCode.PARAM_ERROR.msg
            except ServiceException as exc:
                code, message = exc.code, exc.msg
                if isinstance(exc, PermissionException):
                    status = 401 if code == 401 else 403
                elif code in {ChatErrorCode.PROVIDER_NOT_FOUND.code, ChatErrorCode.MODEL_NOT_FOUND.code,
                              ChatErrorCode.MODEL_MAPPING_NOT_FOUND.code}:
                    status = 404
                elif code in {ChatErrorCode.CONFIG_VERSION_CONFLICT.code, ChatErrorCode.DEFAULT_MODEL_UNAVAILABLE.code,
                              ChatErrorCode.PROVIDER_ALREADY_EXISTS.code, ChatErrorCode.MODEL_ALREADY_EXISTS.code,
                              ChatErrorCode.MODEL_MAPPING_ALREADY_EXISTS.code}:
                    status = 409
                elif code == ChatErrorCode.ADMIN_STORAGE_UNAVAILABLE.code:
                    status = 503
                else:
                    status = 400
            except Exception:
                status, code, message = 500, ResultCode.SYSTEM_ERROR.code, ResultCode.SYSTEM_ERROR.msg
            # 不传 exc/e.errors()，验证异常和数据库错误可能含明文密钥或整个文档。
            warn("admin request rejected.", request_id=request.state.admin_request_id, code=code)
            return JSONResponse(status_code=status, content=R(code=code, msg=message).model_dump())

        return safe_handler
