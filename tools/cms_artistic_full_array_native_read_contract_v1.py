"""Private native consumer unavailable in a public source template."""
PUBLIC_TEMPLATE_ONLY = True

def _same_typed(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def validate_request(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def _object_pairs(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def _non_json_number(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def check_binding(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def _contains_pin(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def _current_pins(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def _verified_qa(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def policy_reasons(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def __getattr__(name):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")
