"""Private native consumer unavailable in a public source template."""
PUBLIC_TEMPLATE_ONLY = True

def load_native_issuer_targets(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def validate_native_issuer_candidate(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def native_release_qa_matches(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def __getattr__(name):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")
