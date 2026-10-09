"""Private native consumer unavailable in a public source template."""
PUBLIC_TEMPLATE_ONLY = True

def require(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def pinned(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def validate_request(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def current_handover(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def independent_QA(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def policy_reasons(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def __getattr__(name):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")
