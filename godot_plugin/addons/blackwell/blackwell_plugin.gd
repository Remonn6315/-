@tool
extends EditorPlugin

## Blackwell Dev-OS — Godot Editor Plugin v1.0
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## Blackwellとリアルタイムで通信するGodotエディタプラグイン。
##
## できること:
##   - エラーログをBlackwellにリアルタイム送信
##   - Blackwellが修正したコードを自動受信・保存
##   - 「このファイルを直して」ボタンでワンクリック修正依頼
##   - シーン構造をBlackwellに送信（地図更新）
##   - Blackwellからの通知をエディタに表示
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const BRIDGE_URL    = "ws://127.0.0.1:9901"
const RECONNECT_SEC = 5.0
const PLUGIN_NAME   = "🤖 Blackwell"

var _ws             : WebSocketPeer = null
var _dock           : Control       = null
var _connected      : bool          = false
var _reconnect_timer: float         = 0.0
var _error_count    : int           = 0
var _pending_writes : Dictionary    = {}   # file_path -> code


# ── 起動 ────────────────────────────────────────────────────

func _enter_tree() -> void:
	_build_dock()
	add_control_to_dock(DOCK_SLOT_RIGHT_BL, _dock)
	_connect_bridge()
	get_editor_interface().get_script_editor().connect(
		"editor_script_changed", _on_script_changed)
	print("[Blackwell] プラグイン起動")


func _exit_tree() -> void:
	if _dock:
		remove_control_from_docks(_dock)
		_dock.queue_free()
	if _ws:
		_ws.close()
	print("[Blackwell] プラグイン終了")


# ── UIドック構築 ─────────────────────────────────────────────

func _build_dock() -> void:
	_dock = preload("blackwell_dock.tscn").instantiate() \
		if ResourceLoader.exists("res://addons/blackwell/blackwell_dock.tscn") \
		else _build_dock_code()


func _build_dock_code() -> Control:
	## tscnがない場合はコードでUIを構築
	var root := VBoxContainer.new()
	root.name        = "BlackwellDock"
	root.custom_minimum_size = Vector2(220, 0)

	# ヘッダー
	var header := Label.new()
	header.text = "🤖 Blackwell Dev-OS"
	header.add_theme_font_size_override("font_size", 13)
	root.add_child(header)

	# 接続状態
	var status_lbl := Label.new()
	status_lbl.name = "StatusLabel"
	status_lbl.text = "⚫ 未接続"
	root.add_child(status_lbl)

	root.add_child(HSeparator.new())

	# ボタン群
	var btn_fix := Button.new()
	btn_fix.name    = "BtnFix"
	btn_fix.text    = "🔧 このファイルを直して"
	btn_fix.tooltip_text = "現在開いているスクリプトの修正をBlackwellに依頼"
	btn_fix.pressed.connect(_on_fix_pressed)
	root.add_child(btn_fix)

	var btn_scene := Button.new()
	btn_scene.name    = "BtnScene"
	btn_scene.text    = "🗺️ シーン情報を送信"
	btn_scene.tooltip_text = "現在のシーン構造をBlackwellのプロジェクト地図に反映"
	btn_scene.pressed.connect(_on_scene_pressed)
	root.add_child(btn_scene)

	var btn_reconnect := Button.new()
	btn_reconnect.name    = "BtnReconnect"
	btn_reconnect.text    = "🔄 再接続"
	btn_reconnect.pressed.connect(_connect_bridge)
	root.add_child(btn_reconnect)

	root.add_child(HSeparator.new())

	# エラーログ表示
	var err_lbl := Label.new()
	err_lbl.text = "最近のエラー:"
	root.add_child(err_lbl)

	var err_list := ItemList.new()
	err_list.name                = "ErrorList"
	err_list.custom_minimum_size = Vector2(0, 120)
	err_list.allow_reselect      = true
	err_list.item_selected.connect(_on_error_selected)
	root.add_child(err_list)

	var btn_fix_error := Button.new()
	btn_fix_error.name    = "BtnFixError"
	btn_fix_error.text    = "⚡ 選択したエラーを自動修正"
	btn_fix_error.pressed.connect(_on_fix_error_pressed)
	root.add_child(btn_fix_error)

	root.add_child(HSeparator.new())

	# ログ
	var log_lbl := Label.new()
	log_lbl.text = "通信ログ:"
	root.add_child(log_lbl)

	var log_box := RichTextLabel.new()
	log_box.name                = "LogBox"
	log_box.custom_minimum_size = Vector2(0, 80)
	log_box.scroll_following    = true
	log_box.bbcode_enabled      = true
	root.add_child(log_box)

	return root


# ── WebSocket接続 ────────────────────────────────────────────

func _connect_bridge() -> void:
	if _ws:
		_ws.close()
	_ws = WebSocketPeer.new()
	var err := _ws.connect_to_url(BRIDGE_URL)
	if err != OK:
		_set_status("⚫ 接続失敗 (port %d)" % 9901)
		_log("接続失敗: error=%d" % err)
	else:
		_log("接続試行中: %s" % BRIDGE_URL)


func _process(delta: float) -> void:
	if not _ws:
		return

	_ws.poll()
	var state := _ws.get_ready_state()

	match state:
		WebSocketPeer.STATE_OPEN:
			if not _connected:
				_connected = true
				_reconnect_timer = 0.0
				_set_status("🟢 接続中")
				_log("Blackwell接続完了！")
				_send_scene_info()

			# 受信処理
			while _ws.get_available_packet_count() > 0:
				var raw  := _ws.get_packet().get_string_from_utf8()
				_handle_message(raw)

		WebSocketPeer.STATE_CLOSED:
			if _connected:
				_connected = false
				_set_status("⚫ 切断")
				_log("切断しました")

			# 自動再接続
			_reconnect_timer += delta
			if _reconnect_timer >= RECONNECT_SEC:
				_reconnect_timer = 0.0
				_connect_bridge()

		WebSocketPeer.STATE_CONNECTING:
			pass


# ── メッセージ受信処理 ────────────────────────────────────────

func _handle_message(raw: String) -> void:
	var msg = JSON.parse_string(raw)
	if not msg:
		return

	var mtype : String = msg.get("type", "")

	match mtype:
		"connected":
			_log("✅ %s" % msg.get("message", ""))

		"write_file":
			## Blackwellが修正したコードを受け取ってファイルに書く
			var file_path : String = msg.get("file", "")
			var code      : String = msg.get("code", "")
			if file_path and code:
				_write_file(file_path, code)
				if msg.get("auto_save", true):
					_reload_script(file_path)
				_log("✅ コード受信・保存: %s" % file_path.get_file())

		"reload":
			var file_path : String = msg.get("file", "")
			_reload_script(file_path)
			_log("🔄 リロード: %s" % (file_path.get_file() if file_path else "全ファイル"))

		"notify":
			var level   : String = msg.get("level", "info")
			var message : String = msg.get("message", "")
			_show_notification(message, level)
			_log("📣 %s" % message)

		"get_scene_info":
			_send_scene_info()

		"pong":
			pass

		_:
			_log("受信: %s" % mtype)


# ── ファイル書き込み ──────────────────────────────────────────

func _write_file(file_path: String, code: String) -> void:
	## res:// パスか絶対パスかを判定して書き込む
	var full_path : String
	if file_path.begins_with("res://"):
		full_path = ProjectSettings.globalize_path(file_path)
	elif file_path.begins_with("/") or file_path.contains(":"):
		full_path = file_path
	else:
		full_path = ProjectSettings.globalize_path("res://" + file_path)

	var f := FileAccess.open(full_path, FileAccess.WRITE)
	if f:
		f.store_string(code)
		f.close()
		_send_json({"type": "file_saved", "file": file_path})
	else:
		_log("❌ 書き込み失敗: %s" % full_path)


func _reload_script(file_path: String) -> void:
	if file_path:
		var res_path : String
		if file_path.begins_with("res://"):
			res_path = file_path
		else:
			res_path = "res://" + file_path.get_file()
		if ResourceLoader.exists(res_path):
			ResourceLoader.load(res_path, "", ResourceLoader.CACHE_MODE_REPLACE)
	get_editor_interface().get_resource_filesystem().scan()


# ── ボタンイベント ────────────────────────────────────────────

func _on_fix_pressed() -> void:
	## 現在開いているスクリプトの修正をBlackwellに依頼
	var script := get_editor_interface().get_script_editor() \
		.get_current_script()
	if not script:
		_log("⚠️ スクリプトが開かれていません")
		return

	var path : String = script.resource_path
	var code : String = script.source_code
	_send_json({
		"type":    "fix_request",
		"file":    path.get_file(),
		"code":    code,
		"problem": "修正が必要です（手動リクエスト）",
		"anchor":  ProjectSettings.get_setting(
			"blackwell/anchor", ""),
	})
	_log("📤 修正リクエスト送信: %s" % path.get_file())
	_show_notification("Blackwellに修正を依頼しました", "info")


func _on_scene_pressed() -> void:
	_send_scene_info()
	_log("📤 シーン情報を送信")


func _on_error_selected(index: int) -> void:
	pass  # 選択状態を保持するだけ


func _on_fix_error_pressed() -> void:
	var err_list : ItemList = _dock.find_child("ErrorList", true, false)
	if not err_list:
		return
	var selected := err_list.get_selected_items()
	if selected.is_empty():
		_log("⚠️ エラーを選択してください")
		return
	var idx    : int    = selected[0]
	var meta             = err_list.get_item_metadata(idx)
	if meta:
		_send_json({
			"type":    "fix_request",
			"file":    meta.get("file", ""),
			"code":    "",
			"problem": meta.get("message", ""),
			"line":    meta.get("line", 0),
		})
		_log("⚡ エラー自動修正依頼: %s" % meta.get("message","")[:50])


func _on_script_changed(script) -> void:
	if script and _connected:
		_log("📄 スクリプト変更: %s" % script.resource_path.get_file())


# ── シーン情報送信 ────────────────────────────────────────────

func _send_scene_info() -> void:
	var scene := get_editor_interface().get_edited_scene_root()
	if not scene:
		return

	var info := {
		"type": "scene_info",
		"data": {
			"scene_name":  scene.name,
			"scene_path":  scene.scene_file_path,
			"node_count":  _count_nodes(scene),
			"root_class":  scene.get_class(),
			"children":    _get_children_info(scene, 0),
		}
	}
	_send_json(info)


func _count_nodes(node: Node) -> int:
	var count := 1
	for child in node.get_children():
		count += _count_nodes(child)
	return count


func _get_children_info(node: Node, depth: int) -> Array:
	if depth > 3:
		return []
	var result := []
	for child in node.get_children():
		result.append({
			"name":     child.name,
			"class":    child.get_class(),
			"script":   child.get_script().resource_path \
				if child.get_script() else "",
			"children": _get_children_info(child, depth + 1),
		})
	return result


# ── エラー検知 ────────────────────────────────────────────────

func _notification(what: int) -> void:
	## エンジンの内部通知を受け取ってエラーを検知
	pass


## Godotのエラーをプラグインが受け取る仕組み:
## Engine.get_main_loop().connect("on_error") は使えないため
## EditorInterface.get_editor_log() を定期ポーリング
var _last_log_line : int = 0

func _poll_error_log() -> void:
	## 未実装のGodot APIのため、代わりにparse_error signalを使う
	pass


# ── UI更新ヘルパー ────────────────────────────────────────────

func _set_status(text: String) -> void:
	if not _dock:
		return
	var lbl : Label = _dock.find_child("StatusLabel", true, false)
	if lbl:
		lbl.text = text


func _log(text: String) -> void:
	print("[Blackwell] %s" % text)
	if not _dock:
		return
	var log_box : RichTextLabel = _dock.find_child("LogBox", true, false)
	if log_box:
		var ts := Time.get_time_string_from_system()
		log_box.append_text("[%s] %s\n" % [ts, text])


func _add_error_to_list(file: String, line: int,
						message: String) -> void:
	if not _dock:
		return
	var err_list : ItemList = _dock.find_child("ErrorList", true, false)
	if not err_list:
		return
	var label := "❌ %s:%d — %s" % [file.get_file(), line, message.substr(0, 40)]
	err_list.add_item(label)
	err_list.set_item_metadata(err_list.get_item_count() - 1, {
		"file": file, "line": line, "message": message
	})
	# 最大20件
	while err_list.get_item_count() > 20:
		err_list.remove_item(0)
	_error_count += 1
	## Blackwellにも送信
	_send_json({
		"type":     "error",
		"file":     file,
		"line":     line,
		"message":  message,
		"severity": "error",
	})


func _show_notification(message: String, level: String) -> void:
	## エディタにポップアップ通知
	match level:
		"error":
			push_error("[Blackwell] " + message)
		"warning":
			push_warning("[Blackwell] " + message)
		_:
			print("[Blackwell] 📣 " + message)


# ── JSON送信 ─────────────────────────────────────────────────

func _send_json(data: Dictionary) -> void:
	if _ws and _ws.get_ready_state() == WebSocketPeer.STATE_OPEN:
		_ws.send_text(JSON.stringify(data))
