import json
import logging
import os
import threading
import uuid
import xml.etree.ElementTree as ET

import stomp


logger = logging.getLogger(__name__)


def _to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _xml_tag_local_name(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


class _ReplyListener(stomp.ConnectionListener):
    def __init__(self, correlation_id):
        self.correlation_id = correlation_id
        self.response_body = None
        self.event = threading.Event()

    def on_message(self, frame):
        incoming_correlation = frame.headers.get("correlation-id")
        if incoming_correlation and incoming_correlation != self.correlation_id:
            return

        self.response_body = frame.body
        self.event.set()

    def on_error(self, frame):
        self.response_body = frame.body
        self.event.set()


class WorkflowAdminService:
    """
    Python equivalent of the C# WorkflowAdminRepository for TIBCO case messaging.
    Uses STOMP over TCP, which TIBCO EMS commonly exposes.
    """

    def __init__(self, settings):
        self.settings = settings

    @classmethod
    def from_config(cls):
        settings = {
            "host": os.environ.get("JMS_HOST", "localhost"),
            "port": int(os.environ.get("JMS_PORT", "7222")),
            "username": os.environ.get("JMS_USERNAME", ""),
            "password": os.environ.get("JMS_PASSWORD", ""),
            "use_ssl": _to_bool(os.environ.get("JMS_USE_SSL"), False),
            "connect_timeout_seconds": int(
                os.environ.get("JMS_CONNECT_TIMEOUT_SECONDS", "10")
            ),
            "reply_timeout_seconds": int(
                os.environ.get("JMS_REPLY_TIMEOUT_SECONDS", "30")
            ),
            "create_case_queue": os.environ.get(
                "JMS_CREATE_CASE_QUEUE", "AJBG.FrameworkServices.CreateCase"
            ),
            "update_case_queue": os.environ.get(
                "JMS_UPDATE_CASE_QUEUE", "AJBG.FrameworkServices.UpdateCase"
            ),
            "reply_queue": os.environ.get(
                "JMS_REPLY_QUEUE", "AJBG.FrameworkServices.Replies"
            ),
            "destination_prefix": os.environ.get("JMS_DESTINATION_PREFIX", "/queue/"),
            "starter_domain": os.environ.get("WORKFLOW_STARTER_DOMAIN", ""),
        }

        config_path = os.environ.get(
            "JMS_CONFIG_PATH",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "jms_credentials.json"),
        )
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as fp:
                    file_settings = json.load(fp)
                if isinstance(file_settings, dict):
                    settings.update({k: v for k, v in file_settings.items() if v is not None})
            except Exception as exc:
                logger.warning(f"Could not read JMS config file at {config_path}: {exc}")

        return cls(settings)

    def post_new_case(self, new_case):
        message_xml = self._build_create_case_xml(new_case)
        reply = self._send_jms_message(self.settings["create_case_queue"], message_xml)
        case_number = self._parse_case_number_from_response(reply)

        response = dict(new_case)
        response["caseNumber"] = int(case_number)
        return response

    def post_update_case(self, message_request):
        if isinstance(message_request, str):
            message_xml = message_request
            case_number = None
        else:
            message_xml = self._build_update_case_xml(message_request)
            case_number = (
                message_request.get("workflowAttributes", {}).get("caseNumber")
                if isinstance(message_request, dict)
                else None
            )

        reply = self._send_jms_message(self.settings["update_case_queue"], message_xml)

        if case_number is not None and str(case_number) not in reply:
            raise RuntimeError(
                f"TIBCO returned an unexpected response for update case {case_number}."
            )

        if case_number is None:
            parsed_case_number = self._parse_case_number_from_response(reply)
            return int(parsed_case_number)

        return int(case_number)

    def _build_create_case_xml(self, new_case):
        case_data = new_case.get("caseData") or []
        start_step = new_case.get("startStep") or ""
        starter = new_case.get("starter") or ""
        started_by = self._normalize_started_by(starter)

        root = ET.Element("workflowMessageRequest")
        attrs = ET.SubElement(root, "workflowAttributes")
        ET.SubElement(attrs, "caseDescription").text = str(
            new_case.get("caseDescription") or ""
        )
        ET.SubElement(attrs, "procedureName").text = str(new_case.get("procedureName") or "")
        ET.SubElement(attrs, "startedBy").text = started_by
        ET.SubElement(attrs, "stepName").text = str(start_step)

        fields_root = ET.SubElement(root, "workflowMessageRequestFields")
        for field in case_data:
            field_node = ET.SubElement(fields_root, "Field")
            ET.SubElement(field_node, "Name").text = str(field.get("fieldName") or "")
            ET.SubElement(field_node, "Value").text = str(field.get("fieldValue") or "")

        return ET.tostring(root, encoding="unicode")

    def _build_update_case_xml(self, message_request):
        root = ET.Element("workflowMessageRequest")

        attrs_node = ET.SubElement(root, "workflowAttributes")
        attrs = message_request.get("workflowAttributes") or {}
        for key, value in attrs.items():
            ET.SubElement(attrs_node, str(key)).text = "" if value is None else str(value)

        fields_node = ET.SubElement(root, "workflowMessageRequestFields")
        field_items = (message_request.get("workflowMessageRequestFields") or {}).get("Field") or []
        for field in field_items:
            field_node = ET.SubElement(fields_node, "Field")
            ET.SubElement(field_node, "Name").text = str(field.get("Name") or "")
            ET.SubElement(field_node, "Value").text = str(field.get("Value") or "")

        return ET.tostring(root, encoding="unicode")

    def _normalize_started_by(self, starter):
        if "\\" in starter:
            return starter.split("\\", 1)[1]
        if self.settings.get("starter_domain"):
            return f"{self.settings['starter_domain']}\\{starter}".split("\\", 1)[1]
        return starter

    def _destination_name(self, queue_name):
        if queue_name.startswith("/"):
            return queue_name
        prefix = self.settings.get("destination_prefix", "/queue/")
        if not prefix.endswith("/"):
            prefix = f"{prefix}/"
        return f"{prefix}{queue_name}"

    def _send_jms_message(self, queue_name, message_text):
        host = self.settings["host"]
        port = int(self.settings["port"])
        username = self.settings.get("username")
        password = self.settings.get("password")
        reply_timeout = int(self.settings.get("reply_timeout_seconds", 30))

        correlation_id = str(uuid.uuid4())
        listener = _ReplyListener(correlation_id)

        connection = stomp.Connection12([(host, port)], keepalive=True)
        connection.set_listener("workflow-admin-reply-listener", listener)
        if _to_bool(self.settings.get("use_ssl"), False):
            connection.set_ssl(for_hosts=[(host, port)])

        try:
            connection.connect(
                login=username,
                passcode=password,
                wait=True,
                headers={"client-id": "case-resubmit-app"},
            )

            reply_destination = self._destination_name(self.settings["reply_queue"])
            subscription_id = f"case-resubmit-{uuid.uuid4()}"
            connection.subscribe(destination=reply_destination, id=subscription_id, ack="auto")

            send_destination = self._destination_name(queue_name)
            connection.send(
                destination=send_destination,
                body=message_text,
                headers={
                    "reply-to": reply_destination,
                    "correlation-id": correlation_id,
                    "persistent": "true",
                    "content-type": "application/xml",
                },
            )

            if not listener.event.wait(timeout=reply_timeout):
                raise TimeoutError(
                    f"Timed out waiting for JMS reply after {reply_timeout} seconds."
                )

            if listener.response_body is None:
                raise RuntimeError("JMS reply listener did not receive a response body.")

            return listener.response_body
        finally:
            try:
                if connection.is_connected():
                    connection.disconnect()
            except Exception:
                pass

    def _parse_case_number_from_response(self, response_xml):
        try:
            root = ET.fromstring(response_xml)
        except ET.ParseError as exc:
            raise RuntimeError(f"Invalid XML response from TIBCO: {exc}") from exc

        for node in root.iter():
            if _xml_tag_local_name(node.tag).lower() == "casenumber" and node.text:
                return node.text.strip()

        raise RuntimeError("Could not find caseNumber in TIBCO response.")
