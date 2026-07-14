extends Node

const BRIDGE_URL := "http://127.0.0.1:8790"
const SCENARIO_PATH := "res://scenario.json"

var headers := PackedStringArray(["Content-Type: application/json"])


func _ready() -> void:
	_run_encounter()


func _run_encounter() -> void:
	var scenario = JSON.parse_string(FileAccess.get_file_as_string(SCENARIO_PATH))
	if not scenario is Dictionary or not scenario.get("event") is Dictionary:
		_fail("invalid benchmark scenario")
		return
	var event: Dictionary = scenario["event"]
	var agents := {}
	for actor_id in event.get("actor_ids", []):
		agents[str(actor_id)] = {"state": "idle"}
	if agents.size() != 2:
		_fail("benchmark scenario requires two agents")
		return
	var decision := await _post(
		"/decision", {"agent_id": scenario.get("agent_id", ""), "event": event}
	)
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
	print(
		"EMPNEON_GODOT_OK scenario=%s decision=%s state=%s"
		% [scenario.get("name", ""), decision["id"], agents[decision["actor_id"]]["state"]]
	)
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
