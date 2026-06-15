"""ASR 工具错误码。"""

ASR_NOT_CONFIGURED = "asr_not_configured"
EXTERNAL_PROCESSING_DISABLED = "external_processing_disabled"
PAID_ASR_DISABLED = "paid_asr_disabled"
BUDGET_EXCEEDED = "budget_exceeded"
ASR_FILE_TOO_LARGE = "asr_file_too_large"
ASR_DURATION_LIMIT_EXCEEDED = "asr_duration_limit_exceeded"
VIDEO_TOO_LONG = "video_too_long"
ASR_PROVIDER_ERROR = "asr_provider_error"
ASR_EMPTY_RESULT = "asr_empty_result"
ASR_INVALID_RESPONSE = "asr_invalid_response"
ASR_DEPENDENCY_MISSING = "asr_dependency_missing"
ASR_MODEL_MISSING = "asr_model_missing"
# 15–120min 中段须 user_confirmed，否则拒绝外部 API
ASR_REQUIRES_USER_CONFIRMATION = "asr_requires_user_confirmation"
# 保留错误码：仅当 async control plane 不可用时回退
ASR_ASYNC_NOT_IMPLEMENTED = "asr_async_not_implemented"
