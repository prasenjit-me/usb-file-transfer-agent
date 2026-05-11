import json
from pathlib import Path
from openai import OpenAI
import usb_manager

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_usb_drives",
            "description": "List all connected USB drives with their labels and free space.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and folders inside a directory path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute directory path to list."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transfer_files",
            "description": (
                "Copy or move files from source_dir to dest_dir. "
                "For a SINGLE specific file use 'filename' (e.g. 'mcp article.md'). "
                "For multiple files by type use 'extension' (e.g. .jpg, .pdf, * for all). "
                "If 'filename' is provided it takes priority over 'extension'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["copy", "move"]},
                    "source_dir": {"type": "string", "description": "Source directory path."},
                    "dest_dir": {"type": "string", "description": "Destination directory path."},
                    "filename": {
                        "type": "string",
                        "description": "Exact filename to transfer (e.g. 'report.pdf'). Use for single-file operations.",
                    },
                    "extension": {
                        "type": "string",
                        "description": "File extension filter like .jpg or * for all files. Ignored when filename is set.",
                    },
                },
                "required": ["action", "source_dir", "dest_dir"],
            },
        },
    },
]


class GrokAgent:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        self.history: list = []

    def _run_tool(self, name: str, args: dict) -> str:
        if name == "list_usb_drives":
            drives = usb_manager.get_usb_drives()
            if not drives:
                return "No USB drives found."
            lines = [
                f"- {d['label']} ({d['mountpoint']}) | Free: {usb_manager.format_size(d['free'])}"
                for d in drives
            ]
            return "\n".join(lines)

        if name == "list_files":
            items = usb_manager.list_directory(args["path"])
            if not items:
                return "Directory is empty or inaccessible."
            lines = [
                f"{'[DIR]' if i['is_dir'] else '[FILE]'} {i['name']}"
                + (f" ({usb_manager.format_size(i['size'])})" if not i['is_dir'] else "")
                for i in items[:60]
            ]
            return "\n".join(lines)

        if name == "transfer_files":
            action = args["action"]
            src = Path(args["source_dir"])
            dst = args["dest_dir"]
            filename = args.get("filename")
            ext = args.get("extension", "*")

            if filename:
                candidate = src / filename
                files = [candidate] if candidate.is_file() else []
                if not files:
                    return f"File '{filename}' not found in {src}."
            else:
                pattern = f"*{ext}" if ext != "*" else "*"
                files = [f for f in src.glob(pattern) if f.is_file()]
                if not files:
                    return f"No files matching '{ext}' found in {src}."

            ok, fail = 0, 0
            fn = usb_manager.copy_file if action == "copy" else usb_manager.move_file
            for f in files:
                success, _ = fn(str(f), dst)
                if success:
                    ok += 1
                else:
                    fail += 1

            return (
                f"{action.capitalize()}d {ok} file(s) to {dst}."
                + (f" {fail} failed." if fail else "")
            )

        return "Unknown tool."

    def _api_call(self, messages: list, *, use_tools: bool = True):
        kwargs: dict = {"model": "llama-3.3-70b-versatile", "messages": messages}
        if use_tools:
            kwargs["tools"] = TOOLS
            kwargs["tool_choice"] = "auto"
        return self.client.chat.completions.create(**kwargs)

    @staticmethod
    def _is_tool_gen_error(exc: Exception) -> bool:
        return "tool_use_failed" in str(exc) or "failed_generation" in str(exc)

    def chat(self, user_message: str, usb_path: str | None, windows_path: str | None) -> str:
        system = (
            "You are a helpful USB file transfer assistant. "
            "Help the user move or copy files between their Windows PC and USB drive. "
            "Be concise. Always confirm the action taken.\n\n"
            "Rules:\n"
            "- When the user names a SPECIFIC file (e.g. 'move report.pdf'), always use the "
            "'filename' parameter of transfer_files — never use 'extension' for single-file requests.\n"
            "- You cannot undo or revert past transfers. If asked, explain that clearly.\n"
            "- Never guess source_dir — use the current paths provided below.\n\n"
            f"Current Windows folder: {windows_path or 'not set'}\n"
            f"Current USB path: {usb_path or 'not selected'}"
        )

        # Build messages without mutating self.history — only commit on success
        messages = [{"role": "system", "content": system}] + self.history + [
            {"role": "user", "content": user_message}
        ]

        try:
            response = self._api_call(messages, use_tools=True)
        except Exception as e:
            if self._is_tool_gen_error(e):
                # Model produced malformed XML-style tool call — retry as plain text
                try:
                    response = self._api_call(messages, use_tools=False)
                except Exception:
                    return "I couldn't process that request. Please try rephrasing."
            else:
                return "Something went wrong connecting to the AI. Please try again."

        msg = response.choices[0].message

        while msg.tool_calls:
            tool_results = []
            for tc in msg.tool_calls:
                try:
                    tool_args = json.loads(tc.function.arguments)
                    result = self._run_tool(tc.function.name, tool_args)
                except (json.JSONDecodeError, KeyError) as e:
                    result = f"Bad tool arguments: {e}"
                tool_results.append({"tool_call_id": tc.id, "role": "tool", "content": result})

            messages.append(msg)
            messages.extend(tool_results)

            try:
                response = self._api_call(messages, use_tools=True)
            except Exception as e:
                if self._is_tool_gen_error(e):
                    return "I had trouble completing that action. Please try rephrasing."
                return "Something went wrong connecting to the AI. Please try again."

            msg = response.choices[0].message

        reply = msg.content or "Done!"
        # Only persist to history after a fully successful round-trip
        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self):
        self.history = []
