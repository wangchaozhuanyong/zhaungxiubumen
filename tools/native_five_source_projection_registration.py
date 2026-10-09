"""Private native consumer unavailable in a public source template."""
PUBLIC_TEMPLATE_ONLY = True

def require(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def canonical(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def pinned(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def validate_entry(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def validate_registration(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def load_five_source_projection_registration(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def validate_five_source_projection_candidate(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def __getattr__(name):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")
