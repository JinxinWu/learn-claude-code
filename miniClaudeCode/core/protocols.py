import uuid


shutdown_requests = {}
plan_requests = {}


def handle_shutdown_request(bus, teammate: str) -> str:
    request_id = str(uuid.uuid4())[:8]
    shutdown_requests[request_id] = {"target": teammate, "status": "pending"}
    bus.send(
        "lead",
        teammate,
        "Please shut down.",
        "shutdown_request",
        {"request_id": request_id},
    )
    return f"Shutdown request {request_id} sent to '{teammate}'"


def handle_plan_review(bus, request_id: str, approve: bool, feedback: str = "") -> str:
    request = plan_requests.get(request_id)
    if not request:
        return f"Error: Unknown plan request_id '{request_id}'"

    request["status"] = "approved" if approve else "rejected"
    bus.send(
        "lead",
        request["from"],
        feedback,
        "plan_approval_response",
        {
            "request_id": request_id,
            "approve": approve,
            "feedback": feedback,
        },
    )
    return f"Plan {request['status']} for '{request['from']}'"
