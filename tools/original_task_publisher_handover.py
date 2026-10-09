"""Private native consumer unavailable in a public source template."""
PUBLIC_TEMPLATE_ONLY = True

def _workflow(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def _admission(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def require(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def pin(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def check_root(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def validate_request(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def control_qa(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def live_adopter(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def validate_event(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def _entry(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def _sequence(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def apply(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def main(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

TASK = "synthetic-deny-only-publisher-handover"
_TASK_DENY_SHA256 = "ab9519afcf80d18db599b123d167b32f5c42862b4f04147554d460539ebfa11d"
POLICY_KEY = "original_task_publisher_execution_only_handover"


def _private_task(value):
    import hashlib
    return (isinstance(value, str) and (value == TASK
            or hashlib.sha256(value.encode()).hexdigest() == _TASK_DENY_SHA256))


def _has_handover(value):
    if isinstance(value, dict):
        if (POLICY_KEY in value or value.get("publisher_execution_handover")
                or _private_task(value.get("task_id"))):
            return True
        return any(_has_handover(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_handover(item) for item in value)
    return False


def _ordinary_context(root, task_id=None, snapshot=None, receipts=None, receipt=None):
    from pathlib import Path
    import workflow_control as workflow
    if _private_task(task_id) or _has_handover([snapshot, receipts, receipt]):
        raise workflow.WorkflowError("public_template_has_no_native_authorization")
    policy = workflow.load_policy(Path(root))
    events = workflow.read_jsonl(Path(root) / workflow.WORKFLOW_EVENTS)
    if _has_handover(policy) or _has_handover(events):
        raise workflow.WorkflowError("public_template_has_no_native_authorization")


def binding(root, task_id, receipts=None):
    _ordinary_context(root, task_id, receipts=receipts)
    return None


def replay(root, snapshot):
    _ordinary_context(root, snapshot=snapshot)
    return None


def legacy_context(root, snapshot, receipts):
    _ordinary_context(root, snapshot=snapshot, receipts=receipts)
    return snapshot, receipts


def validate_new_receipt(root, snapshot, receipts, receipt):
    _ordinary_context(root, snapshot=snapshot, receipts=receipts, receipt=receipt)
    return False


def progress(root, task_id, action_id, scope):
    _ordinary_context(root, task_id)
    return None


def recoverable_dispatch(root, snapshot, receipts, sent):
    _ordinary_context(root, snapshot=snapshot, receipts=receipts, receipt=sent)
    return False


def retry_projection(root, task_id, action_id, scope, receipt_id, approval_id):
    _ordinary_context(root, task_id)
    return None


def dispatch_precheck(root, snapshot, department, thread, action_id, scope):
    _ordinary_context(root, snapshot=snapshot)
    return []


def shadow_projection(root, task_id):
    _ordinary_context(root, task_id)
    return None

def __getattr__(name):
    raise AttributeError(name)
