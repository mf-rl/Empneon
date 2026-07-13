extends Node

const BRIDGE_URL := "http://127.0.0.1:8790"

var headers := PackedStringArray(["Content-Type: application/json"])
var agents := {
	"godot-a": {"state": "idle"},
	"godot-b": {"state": "idle"},
}


func _ready() -> void:
	_run_encounter()


func _run_encounter() -> void:
	var event := {
		"id": "godot-encounter-1",
		"type": "encounter",
		"actor_ids": ["godot-a", "godot-b"],
		"location": "godot-square",
		"facts": {"distance": 1},
		"happened_at": 1,
	}
	var decision := await _post("/decision", {"agent_id": "godot-a", "event": event})
	if decision.is_empty() or decision.get("intent") != "acknowledge":
		_fail("invalid decision")
		return
	agents[decision["actor_id"]]["state"] = "aware"
	var result := await _post("/result", {
		"decision_id": decision["id"],
		"status": "succeeded",
		"applied_changes": [{
			"path": "awareness.%s" % decision["target_id"],
			"operation": "set",
			"value": true,
		}],
	})
	if not result.get("accepted", false):
		_fail("result was not accepted")
		return
	print("EMPNEON_GODOT_OK decision=%s state=%s" % [decision["id"], agents["godot-a"]["state"]])
	get_tree().quit(0)


func _post(path: String, payload: Dictionary) -> Dictionary:
	var request := HTTPRequest.new()
	request.timeout = 5.0
	add_child(request)
	var error := request.request(
		BRIDGE_URL + path,
		headers,
		HTTPClient.METHOD_POST,
		JSON.stringify(payload),
	)
	if error != OK:
		request.queue_free()
		return {}
	var response: Array = await request.request_completed
	request.queue_free()
	if response[1] != 200:
		return {}
	var parsed = JSON.parse_string(response[3].get_string_from_utf8())
	return parsed if parsed is Dictionary else {}


func _fail(message: String) -> void:
	push_error(message)
	get_tree().quit(1)
