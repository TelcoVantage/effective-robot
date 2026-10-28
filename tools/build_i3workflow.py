#!/usr/bin/env python3
"""
Builds the "Dropped Call Monitor" Architect workflow as an .i3WorkFlow file
(the format the Architect UI imports via Save menu > Import).

An .i3WorkFlow file is base64( encodeURIComponent( compact JSON ) ).  The JSON
shape mirrors a real Architect export (Genesys Cloud blueprint exports were used
as the reference for every object type produced here).

Run:  python3 tools/build_i3workflow.py
Writes:
  genesys/3-workflow/Dropped Call Monitor.i3WorkFlow
  genesys/3-workflow/Dropped Call Monitor.i3WorkFlow.decoded.json   (readable copy)
"""
import base64
import json
import os
import urllib.parse
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "genesys", "3-workflow")

FLOW_NAME = "Dropped Call Monitor"
FLOW_DESCRIPTION = (
    "Triggered by v2.detail.events.conversation.{id}.customer.end for voice calls that "
    "ended with an our-side disconnect type. Reads the ErrorCode / ErrorMessage "
    "participant attributes and writes a row to the 'Dropped Call Log' data table."
)
INTEGRATION_NAME = "Genesys Cloud Data Actions"   # category = name of the data actions integration
ACTION_GET = "Get Conversation Drop Details"
ACTION_WRITE = "Write Dropped Call Log Row"

# Same error schema Architect attaches to every Genesys Cloud data action
ERROR_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "ErrorBody",
    "description": "Detailed information about an error response.",
    "type": "object",
    "required": ["errorCode", "status", "userMessage"],
    "properties": {
        "errors": {"type": "array", "items": {"type": "object"}, "name": "errors", "required": False},
        "errorCode": {"description": "A code unique to this error.", "type": "string", "name": "errorCode", "required": False},
        "status": {"description": "The HTTP status code for this message (400, 401, 403, 404, 500, etc.)", "type": "integer", "name": "status", "required": False},
        "correlationId": {"description": "The correlation Id or context Id for this message. If left blank the Public API will look at the HTTP response header 'ININ-Correlation-Id' instead.", "type": "string", "name": "correlationId", "required": False},
        "entityId": {"description": "The ID of the entity this error refers to. Only used in BackendErrorBody instances within the errors array.", "type": "string", "name": "entityId", "required": False},
        "entityName": {"description": "The name of the entity this error refers to. Only used in BackendErrorBody instances within the errors array.", "type": "string", "name": "entityName", "required": False},
        "userMessage": {"description": "A customer friendly message. This should be a complete sentence, use proper grammar and only include information useful to a customer. This is not a dev message and should not include things like Org Id", "type": "string", "name": "userMessage", "required": False},
        "userParamsMessage": {"description": "This is the same as message except it uses template fields for variable replacement. For instance: 'User {username} was not found'", "type": "string", "name": "userParamsMessage", "required": False},
        "userParams.key": {"description": "Used in conjunction with userParamsMessage. These are the template parameters. For instance: UserParam.key = 'username', UserParam.value = 'john.doe'", "type": "array", "items": {"description": "Key name of userParam  pair.", "type": "string"}, "name": "userParams.key", "required": False},
        "userParams.value": {"description": "Used in conjunction with userParamsMessage. These are the template parameters. For instance: UserParam.key = 'username', UserParam.value = 'john.doe'", "type": "array", "items": {"description": "Value of userParam  pair.", "type": "string"}, "name": "userParams.value", "required": False},
        "details.errorCode": {"type": "array", "items": {"type": "string"}, "name": "details.errorCode", "required": False},
        "details.fieldName": {"type": "array", "items": {"type": "string"}, "name": "details.fieldName", "required": False},
        "details.entityId": {"type": "array", "items": {"type": "string"}, "name": "details.entityId", "required": False},
        "details.entityName": {"type": "array", "items": {"type": "string"}, "name": "details.entityName", "required": False},
    },
    "additionalProperties": False,
}
ERROR_BINDING_TYPES = [
    ("errorCode", "str"), ("status", "int"), ("correlationId", "str"), ("entityId", "str"),
    ("entityName", "str"), ("userMessage", "str"), ("userParamsMessage", "str"),
    ("userParams.key", "str_coll"), ("userParams.value", "str_coll"),
    ("details.errorCode", "str_coll"), ("details.fieldName", "str_coll"),
    ("details.entityId", "str_coll"), ("details.entityName", "str_coll"),
]


def gid():
    return str(uuid.uuid4())


# --------------------------------------------------------------------------
# Variables
# --------------------------------------------------------------------------
class Var:
    def __init__(self, name, is_input=False, initial=None):
        self.name = name
        self.id = gid()
        self.is_input = is_input
        self.initial = initial  # None -> empty/NOT_SET, str -> literal

    def definition(self):
        if self.initial is None:
            init = value_empty("str")
        else:
            init = value_literal(self.initial)
        return {
            "id": self.id,
            "isCollection": False,
            "isInternal": False,
            "isOutput": False,
            "isInput": self.is_input,
            "isSecure": False,
            "version": "1.0",
            "__type": "StringVariable",
            "name": self.name,
            "initialValue": init,
        }

    def reference(self):
        return {"id": self.id, "type": "str", "isSysRef": False, "name": self.name}


# --------------------------------------------------------------------------
# Value wrappers (the {config,text,type,uiMetaData,metaData,version} objects)
# mode 0 = expression, 1 = literal, 2 = variable, 3 = no value
# --------------------------------------------------------------------------
def value_empty(vtype):
    return {
        "config": {"emp": {"pos": 1, "text": "", "type": vtype}},
        "text": "", "type": vtype,
        "uiMetaData": {"mode": 3}, "metaData": {}, "version": 2,
    }


def value_literal(text, vtype="str"):
    return {
        "config": {"lit": {"pos": 1, "text": text, "type": vtype}},
        "text": text, "type": vtype,
        "uiMetaData": {"mode": 1}, "metaData": {}, "version": 2,
    }


def value_var(var, mode):
    """mode 2 = variable binding (outputs / update targets), mode 0 = expression that is a variable"""
    return {
        "config": {"ref": {"pos": 1, "text": var.name, "type": "str", "val": var.id}},
        "text": var.name, "type": "str",
        "uiMetaData": {"mode": mode},
        "metaData": {"references": [var.reference()]},
        "version": 2,
    }


# --------------------------------------------------------------------------
# Expression builder: renders Architect expression text AND the parsed tree
# that Architect stores next to it (positions are 1-based character offsets).
# --------------------------------------------------------------------------
class Ref:
    def __init__(self, var):
        self.var = var

    def emit(self, pos, refs):
        if self.var.id not in [r["id"] for r in refs]:
            refs.append(self.var.reference())
        return self.var.name, {"ref": {"pos": pos, "text": self.var.name, "type": "str", "val": self.var.id}}


class Lit:
    def __init__(self, value):
        self.value = value  # str or bool

    def emit(self, pos, refs):
        if isinstance(self.value, bool):
            t = "true" if self.value else "false"
            return t, {"lit": {"pos": pos, "text": t, "type": "bln"}}
        escaped = self.value.replace("\\", "\\\\").replace('"', '\\"')
        return '"' + escaped + '"', {"lit": {"pos": pos, "text": self.value, "type": "str"}}


class Func:
    def __init__(self, name, args, rtype):
        self.name, self.args, self.rtype = name, args, rtype

    def emit(self, pos, refs):
        text = self.name + "("
        cur = pos + len(text)
        operands = []
        for i, a in enumerate(self.args):
            if i:
                text += ", "
                cur += 2
            t, node = a.emit(cur, refs)
            text += t
            cur += len(t)
            operands.append(node)
        text += ")"
        return text, {self.name: {"pos": pos, "operands": operands, "type": self.rtype}}


class Eq:
    def __init__(self, left, right):
        self.left, self.right = left, right

    def emit(self, pos, refs):
        lt, ln = self.left.emit(pos, refs)
        op_pos = pos + len(lt) + 1
        rt, rn = self.right.emit(op_pos + 3, refs)
        return lt + " == " + rt, {"==": {"pos": op_pos, "operands": [ln, rn], "type": "bln"}}


def If(cond, a, b, rtype):
    return Func("If", [cond, a, b], rtype)


def expression(node, rtype):
    refs = []
    text, cfg = node.emit(1, refs)
    key = next(iter(cfg))
    cfg[key]["text"] = text
    return {
        "config": cfg, "text": text, "type": rtype,
        "uiMetaData": {"mode": 0},
        "metaData": {"references": refs},
        "version": 2,
    }


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------
class Tracker:
    n = 10

    @classmethod
    def next(cls):
        cls.n += 1
        return cls.n - 1


def base_action(name, atype):
    return {"trackingId": Tracker.next(), "id": gid(), "name": name,
            "uiMetaData": {"collapsed": False}, "__type": atype}


def action_data(name, action_def, inputs, outputs, paths, next_action=None):
    """inputs: {contractInput: valueWrapper}; outputs: {contractOutput: Var}; paths: {Success/Failure/Timeout: action-id or None}"""
    a = base_action(name, "DataAction")
    a.update({
        "actionName": action_def["name"],
        "actionId": action_def["id"],
        "category": {"id": INTEGRATION_NAME, "name": INTEGRATION_NAME},
        "useSuggestedTimeout": True,
    })
    if next_action:
        a["nextAction"] = next_action
    a["errorBindings"] = [{"name": n, "value": value_empty(t)} for n, t in ERROR_BINDING_TYPES]
    a["processingPrompt"] = value_empty("pmt")
    a["inputs"] = [{"name": k, "value": v} for k, v in inputs.items()]
    a["outputs"] = [{"name": k, "value": value_var(v, 2)} for k, v in outputs.items()]
    a["timeout"] = {
        "config": {"lit": {"pos": 1, "text": "P0D0H1M0S0F", "type": "dur"}},
        "text": "P0D0H1M0S0F", "type": "dur",
        "uiMetaData": {"mode": 1}, "metaData": {}, "version": 2,
    }
    a["paths"] = []
    for label, oid in (("Success", "__SUCCESS__"), ("Failure", "__FAILURE__"), ("Timeout", "__TIMEOUT__")):
        p = {"label": label, "outputId": oid, "uiMetaData": {"collapsed": False}}
        if paths.get(label):
            p = {"nextActionId": paths[label], **p}
        a["paths"].append(p)
    return a


def action_update(name, assignments, next_action=None):
    """assignments: list of (Var, expressionWrapper)"""
    a = base_action(name, "UpdateVariableAction")
    if next_action:
        a["nextAction"] = next_action
    a["variables"] = [{"expression": e, "variable": value_var(v, 2)} for v, e in assignments]
    return a


def action_decision(name, expr, yes_next=None, no_next=None, next_action=None):
    a = base_action(name, "DecisionAction")
    if next_action:
        a["nextAction"] = next_action
    a["expression"] = expr
    yes = {"label": "Yes", "outputId": "__YES__", "uiMetaData": {"collapsed": False}}
    no = {"label": "No", "outputId": "__NO__", "uiMetaData": {"collapsed": False}}
    if yes_next:
        yes = {"nextActionId": yes_next, **yes}
    if no_next:
        no = {"nextActionId": no_next, **no}
    a["paths"] = [yes, no]
    return a


def action_end(name, exit_reason=None):
    a = base_action(name, "EndWorkflowAction")
    a["exitReason"] = value_literal(exit_reason) if exit_reason else value_empty("str")
    return a


# --------------------------------------------------------------------------
# Data action contracts (must match genesys/1-data-actions/*.json)
# --------------------------------------------------------------------------
def flat_props(names):
    return {n: {"type": "string", "name": n, "required": False} for n in names}


GET_INPUTS = ["CONVERSATION_ID"]
GET_OUTPUTS = ["errorCode", "errorMessage", "callStartTime", "callEndTime", "queueName", "agentName"]
WRITE_INPUTS = ["TABLE_ID", "KEY", "CALL_START_TIME", "CALL_END_TIME", "DISCONNECT_TYPE", "DROP_CATEGORY",
                "ERROR_CODE", "ERROR_MESSAGE", "DIRECTION", "ANI", "DNIS", "QUEUE_NAME", "AGENT_NAME",
                "LOOKUP_STATUS"]


def action_service_entry(name, inputs, outputs):
    input_schema = {"type": "object", "properties": flat_props(inputs), "additionalProperties": True}
    success_schema = {"type": "object", "properties": flat_props(outputs), "additionalProperties": True}
    return {
        "id": "custom_-_" + gid(),
        "name": name,
        "category": INTEGRATION_NAME,
        "contract": {
            "input": {"inputSchemaFlattened": {"schema": input_schema}},
            "output": {
                "errorSchemaFlattened": {"schema": ERROR_SCHEMA},
                "successSchemaFlattened": {"schema": success_schema},
            },
        },
        "result": "ok",
        "inputSchema": input_schema,
        "successSchema": success_schema,
        "errorSchema": ERROR_SCHEMA,
    }


# --------------------------------------------------------------------------
# Build the flow
# --------------------------------------------------------------------------
def build():
    # --- variables -------------------------------------------------------
    # Inputs: names MUST match top-level primitives of the customer.end event
    v_conversationId = Var("Flow.conversationId", is_input=True)
    v_participantId = Var("Flow.participantId", is_input=True)
    v_sessionId = Var("Flow.sessionId", is_input=True)
    v_disconnectType = Var("Flow.disconnectType", is_input=True)
    v_mediaType = Var("Flow.mediaType", is_input=True)
    v_direction = Var("Flow.direction", is_input=True)
    v_ani = Var("Flow.ani", is_input=True)
    v_dnis = Var("Flow.dnis", is_input=True)
    v_provider = Var("Flow.provider", is_input=True)
    # Settings (edit the initial value in Architect after import)
    v_logTableId = Var("Flow.logTableId", initial="REPLACE_WITH_DATA_TABLE_ID")
    v_logWhenNoErrorAttribute = Var("Flow.logWhenNoErrorAttribute", initial="false")
    # Working variables
    v_errorCode = Var("Flow.errorCode")
    v_errorMessage = Var("Flow.errorMessage")
    v_callStartTime = Var("Flow.callStartTime")
    v_callEndTime = Var("Flow.callEndTime")
    v_queueName = Var("Flow.queueName")
    v_agentName = Var("Flow.agentName")
    v_dropCategory = Var("Flow.dropCategory")
    v_lookupStatus = Var("Flow.lookupStatus")

    variables = [v_conversationId, v_participantId, v_sessionId, v_disconnectType, v_mediaType,
                 v_direction, v_ani, v_dnis, v_provider, v_logTableId, v_logWhenNoErrorAttribute,
                 v_errorCode, v_errorMessage, v_callStartTime, v_callEndTime, v_queueName,
                 v_agentName, v_dropCategory, v_lookupStatus]

    # --- data action definitions ----------------------------------------
    da_get = action_service_entry(ACTION_GET, GET_INPUTS, GET_OUTPUTS)
    da_write = action_service_entry(ACTION_WRITE, WRITE_INPUTS, [])

    # --- actions (built bottom-up so ids are known for linking) ----------
    # 7. End
    end_logged = action_end("End - row logged", "Logged")
    end_write_failed = action_end("End - log write failed", "LogWriteFailed")
    end_write_timeout = action_end("End - log write timed out", "LogWriteTimeout")
    end_no_error = action_end("End - no error attribute", "NoErrorAttribute")

    # 6. Write the log row
    write_inputs = {
        "TABLE_ID": value_var(v_logTableId, 0),
        "KEY": value_var(v_conversationId, 0),
        "CALL_START_TIME": value_var(v_callStartTime, 0),
        "CALL_END_TIME": value_var(v_callEndTime, 0),
        "DISCONNECT_TYPE": value_var(v_disconnectType, 0),
        "DROP_CATEGORY": value_var(v_dropCategory, 0),
        "ERROR_CODE": value_var(v_errorCode, 0),
        "ERROR_MESSAGE": value_var(v_errorMessage, 0),
        "DIRECTION": value_var(v_direction, 0),
        "ANI": value_var(v_ani, 0),
        "DNIS": value_var(v_dnis, 0),
        "QUEUE_NAME": value_var(v_queueName, 0),
        "AGENT_NAME": value_var(v_agentName, 0),
        "LOOKUP_STATUS": value_var(v_lookupStatus, 0),
    }
    write_row = action_data(
        "Write Dropped Call Log row", da_write, write_inputs, {},
        {"Success": None, "Failure": end_write_failed["id"], "Timeout": end_write_timeout["id"]},
        next_action=end_logged["id"],
    )

    # 5. Should we log when there is no error attribute?
    log_anyway_expr = expression(
        If(Eq(Ref(v_logWhenNoErrorAttribute), Lit("true")), Lit(True),
           If(Eq(Ref(v_lookupStatus), Lit("OK")), Lit(False), Lit(True), "bln"), "bln"),
        "bln")
    log_anyway = action_decision("Log anyway (setting on, or lookup failed)?", log_anyway_expr,
                                 yes_next=None, no_next=end_no_error["id"])

    # 4. Is the error attribute empty?
    no_error_expr = expression(Func("IsNotSetOrEmpty", [Ref(v_errorCode)], "bln"), "bln")
    no_error = action_decision("No error attribute on the call?", no_error_expr,
                               yes_next=log_anyway["id"], no_next=None,
                               next_action=write_row["id"])

    # 3. Classify the disconnect type into a readable category
    def cat(code, label, else_node):
        return If(Eq(Ref(v_disconnectType), Lit(code)), Lit(label), else_node, "str")

    classify_node = cat("ERROR", "Platform error (ERROR)",
                 cat("SYSTEM", "System disconnect (SYSTEM)",
                 cat("TIMEOUT", "Timeout (TIMEOUT)",
                 cat("TRANSPORT_FAILURE", "Transport failure (TRANSPORT_FAILURE)",
                 cat("PEER", "Disconnected by our participant (PEER)",
                 cat("CLIENT", "Disconnected by client or API (CLIENT)",
                     Ref(v_disconnectType)))))))
    classify = action_update("Classify drop category",
                             [(v_dropCategory, expression(classify_node, "str"))],
                             next_action=no_error["id"])

    # 2. Lookup result markers (plain literals -> stored as literal values, mode 1)
    mark_ok = action_update("Lookup OK", [(v_lookupStatus, value_literal("OK"))])
    mark_failed = action_update("Lookup failed", [
        (v_lookupStatus, value_literal("LOOKUP_FAILED")),
        (v_errorMessage, value_literal("Could not read the conversation. Check the data action, its OAuth client permissions and the integration status.")),
    ])
    mark_timeout = action_update("Lookup timed out", [
        (v_lookupStatus, value_literal("LOOKUP_TIMEOUT")),
        (v_errorMessage, value_literal("Conversation lookup timed out.")),
    ])

    # 1. Read the conversation (participant attributes, times, queue, agent)
    get_details = action_data(
        "Get conversation drop details", da_get,
        {"CONVERSATION_ID": value_var(v_conversationId, 0)},
        {"errorCode": v_errorCode, "errorMessage": v_errorMessage, "callStartTime": v_callStartTime,
         "callEndTime": v_callEndTime, "queueName": v_queueName, "agentName": v_agentName},
        {"Success": mark_ok["id"], "Failure": mark_failed["id"], "Timeout": mark_timeout["id"]},
        next_action=classify["id"],
    )

    action_list = [get_details, mark_ok, mark_failed, mark_timeout, classify, no_error, log_anyway,
                   end_no_error, write_row, end_write_failed, end_write_timeout, end_logged]

    state = {
        "startAction": get_details["id"],
        "trackingId": Tracker.next(),
        "id": gid(),
        "name": "Initial State",
        "uiMetaData": {"collapsed": False},
        "__type": "State",
        "actionList": action_list,
        "variables": [],
    }

    flow = {
        "nextTrackingNumber": Tracker.next(),
        "defaultLanguage": "en-US",
        "description": FLOW_DESCRIPTION,
        "initialSequence": state["id"],
        "name": FLOW_NAME,
        "uiMetaData": {"bridgeServerActions": [], "screenPops": [], "actionServiceActions": [da_get, da_write], "state": []},
        "supportedLanguages": ["en-US"],
        "manifest": {
            "dataAction": [
                {"name": da_get["name"], "id": da_get["id"],
                 "context": [{"actionName": get_details["name"], "id": get_details["id"], "name": get_details["name"]}]},
                {"name": da_write["name"], "id": da_write["id"],
                 "context": [{"actionName": write_row["name"], "id": write_row["id"], "name": write_row["name"]}]},
            ],
            "language": [{"id": "en-US"}],
            "userPrompt": [],
            "systemPrompt": [],
        },
        "type": "workflow",
        "debugSettings": {},
        "errorHandling": {
            "queue": {
                "config": {"emp": {"pos": 1, "text": "", "type": "que"}},
                "text": "", "type": "que", "uiMetaData": {"mode": 1}, "metaData": {}, "version": 2,
                "outOfService": True,
            },
            "handlingType": "EndWorkflow",
        },
        "defaultSettings": {},
        "flowMetaData": {"flowDocumentVersion": "1.0", "minimumServerVersion": "1.0", "ttsDataVersion": "1.0"},
        "flowSequenceItemList": [state],
        "supportedLanguageOptions": [{"language": "en-US"}],
        "variables": [v.definition() for v in variables],
    }
    return flow


def encode(flow):
    compact = json.dumps(flow, separators=(",", ":"), ensure_ascii=False)
    # encodeURIComponent-compatible percent encoding, then base64
    quoted = urllib.parse.quote(compact, safe="-_.!~*'()")
    return base64.b64encode(quoted.encode("utf-8")).decode("ascii")


def main():
    flow = build()
    os.makedirs(OUT_DIR, exist_ok=True)
    i3_path = os.path.join(OUT_DIR, FLOW_NAME + ".i3WorkFlow")
    with open(i3_path, "w", newline="") as f:
        f.write(encode(flow))
    with open(os.path.join(OUT_DIR, FLOW_NAME + ".i3WorkFlow.decoded.json"), "w") as f:
        json.dump(flow, f, indent=2)
    print("wrote", i3_path)


if __name__ == "__main__":
    main()
