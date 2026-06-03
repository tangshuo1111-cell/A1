"""V16 R4-C / R5-C：ASR 工具错误码。"""

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
# V16-R5C：15-120min 中段必须人工确认，未确认拒绝外部 API 调用
ASR_REQUIRES_USER_CONFIRMATION = "asr_requires_user_confirmation"
# V16-R5C：长音频/视频异步任务路径（CreateRecTask + DescribeTaskStatus）尚未实现
ASR_ASYNC_NOT_IMPLEMENTED = "asr_async_not_implemented"
