"""Private native consumer unavailable in a public source template."""
PUBLIC_TEMPLATE_ONLY = True

class AdmissionError:
    def __init__(self,*args,**kwargs):
        raise ValueError('public_template_has_no_native_authorization')

def require(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def pinned_json(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def validate_entry(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def validate_manifest(*args, **kwargs):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")

def __getattr__(name):
    from workflow_control import WorkflowError
    raise WorkflowError("public_template_has_no_native_authorization")
