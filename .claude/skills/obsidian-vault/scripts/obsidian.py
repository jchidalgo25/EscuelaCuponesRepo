#!/usr/bin/env python3
"""Cliente mínimo para leer/escribir notas en una bóveda de Obsidian.

Soporta dos modos de conexión (se elige automáticamente):

  1. REST  -> plugin "Local REST API" de Obsidian.
             Variables: OBSIDIAN_API_URL (ej. https://127.0.0.1:27124)
                        OBSIDIAN_API_KEY
                        OBSIDIAN_VERIFY_SSL=0 (por defecto; el plugin usa cert autofirmado)
  2. FS    -> acceso directo a la carpeta de la bóveda.
             Variable:  OBSIDIAN_VAULT_PATH (ej. /home/yo/Documentos/MiBoveda)

Si están ambas, se usa REST salvo que OBSIDIAN_MODE=fs.
Las variables también pueden ir en un archivo .claude/obsidian.env (KEY=VALUE).

Uso:
  obsidian.py check
  obsidian.py read   <ruta.md>
  obsidian.py write  <ruta.md>   [--file F | stdin]   (crea o sobrescribe)
  obsidian.py append <ruta.md>   [--file F | stdin]   (agrega al final; crea si no existe)
  obsidian.py list   [carpeta]
  obsidian.py search <texto>
  obsidian.py exists <ruta.md>

Sin dependencias externas: solo biblioteca estándar.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def load_env_file():
    """Carga .claude/obsidian.env (si existe) sin pisar variables ya definidas."""
    candidates = [
        Path.cwd() / ".claude" / "obsidian.env",
        SKILL_DIR.parent.parent / "obsidian.env",
        Path.home() / ".claude" / "obsidian.env",
    ]
    for env_file in candidates:
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        break


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def clean_path(note_path):
    p = note_path.strip().lstrip("/").replace("\\", "/")
    if ".." in Path(p).parts:
        die(f"Ruta no permitida: {note_path}")
    return p


# --------------------------------------------------------------------------- FS
class FsVault:
    def __init__(self, root):
        self.root = Path(os.path.expanduser(root)).resolve()
        if not self.root.is_dir():
            die(f"OBSIDIAN_VAULT_PATH no existe o no es carpeta: {self.root}")

    def describe(self):
        return f"modo=fs bóveda={self.root}"

    def _p(self, note_path):
        return self.root / clean_path(note_path)

    def exists(self, note_path):
        return self._p(note_path).is_file()

    def read(self, note_path):
        p = self._p(note_path)
        if not p.is_file():
            die(f"No existe la nota: {note_path}", 2)
        return p.read_text(encoding="utf-8")

    def write(self, note_path, content):
        p = self._p(note_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def append(self, note_path, content):
        p = self._p(note_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        prefix = ""
        if p.is_file():
            existing = p.read_text(encoding="utf-8")
            if existing and not existing.endswith("\n"):
                prefix = "\n"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(prefix + content)

    def list(self, folder=""):
        base = self._p(folder) if folder else self.root
        if not base.is_dir():
            die(f"No existe la carpeta: {folder}", 2)
        out = []
        for child in sorted(base.iterdir()):
            if child.name.startswith("."):
                continue
            out.append(child.name + ("/" if child.is_dir() else ""))
        return out

    def search(self, query):
        q = query.lower()
        hits = []
        for md in self.root.rglob("*.md"):
            if any(part.startswith(".") for part in md.relative_to(self.root).parts):
                continue
            try:
                text = md.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = md.relative_to(self.root).as_posix()
            if q in rel.lower():
                hits.append(rel)
                continue
            for line in text.splitlines():
                if q in line.lower():
                    hits.append(f"{rel}: {line.strip()[:160]}")
                    break
        return hits


# ------------------------------------------------------------------------- REST
class RestVault:
    def __init__(self, url, key):
        self.url = url.rstrip("/")
        self.key = key
        verify = os.environ.get("OBSIDIAN_VERIFY_SSL", "0") not in ("0", "false", "no", "")
        self.ctx = ssl.create_default_context() if verify else ssl._create_unverified_context()

    def describe(self):
        return f"modo=rest api={self.url}"

    def _req(self, method, path, body=None, content_type="text/markdown", accept=None):
        req = urllib.request.Request(self.url + path, method=method)
        req.add_header("Authorization", f"Bearer {self.key}")
        if body is not None:
            req.data = body.encode("utf-8")
            req.add_header("Content-Type", content_type)
        if accept:
            req.add_header("Accept", accept)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=20) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            die(f"No se pudo conectar con Obsidian en {self.url}: {e.reason}. "
                "¿Está Obsidian abierto y el plugin Local REST API activo?")

    def _vault(self, note_path, folder=False):
        p = urllib.parse.quote(clean_path(note_path))
        return "/vault/" + p + ("/" if folder and p else "")

    def check(self):
        status, body = self._req("GET", "/")
        if status != 200:
            die(f"Respuesta inesperada ({status}): {body[:200]}")
        data = json.loads(body)
        if not data.get("authenticated"):
            die("La API respondió pero la API key no es válida (authenticated=false).")
        return data

    def exists(self, note_path):
        status, _ = self._req("GET", self._vault(note_path))
        return status == 200

    def read(self, note_path):
        status, body = self._req("GET", self._vault(note_path))
        if status == 404:
            die(f"No existe la nota: {note_path}", 2)
        if status != 200:
            die(f"Error leyendo ({status}): {body[:200]}")
        return body

    def write(self, note_path, content):
        status, body = self._req("PUT", self._vault(note_path), content)
        if status not in (200, 204):
            die(f"Error escribiendo ({status}): {body[:200]}")

    def append(self, note_path, content):
        status, body = self._req("POST", self._vault(note_path), content)
        if status not in (200, 204):
            die(f"Error agregando ({status}): {body[:200]}")

    def list(self, folder=""):
        status, body = self._req("GET", self._vault(folder, folder=True) if folder else "/vault/")
        if status == 404:
            die(f"No existe la carpeta: {folder}", 2)
        if status != 200:
            die(f"Error listando ({status}): {body[:200]}")
        return json.loads(body).get("files", [])

    def search(self, query):
        q = urllib.parse.quote(query)
        status, body = self._req("POST", f"/search/simple/?query={q}&contextLength=80")
        if status != 200:
            die(f"Error buscando ({status}): {body[:200]}")
        hits = []
        for item in json.loads(body):
            ctx = ""
            if item.get("matches"):
                ctx = item["matches"][0].get("context", "").replace("\n", " ").strip()
            hits.append(f"{item['filename']}: {ctx[:160]}" if ctx else item["filename"])
        return hits


# ------------------------------------------------------------------------- main
def get_vault():
    load_env_file()
    mode = os.environ.get("OBSIDIAN_MODE", "").lower()
    url = os.environ.get("OBSIDIAN_API_URL")
    key = os.environ.get("OBSIDIAN_API_KEY")
    path = os.environ.get("OBSIDIAN_VAULT_PATH")
    if mode != "fs" and url and key:
        return RestVault(url, key)
    if mode != "rest" and path:
        return FsVault(path)
    die("Obsidian no está configurado. Define OBSIDIAN_VAULT_PATH (modo carpeta) "
        "o OBSIDIAN_API_URL + OBSIDIAN_API_KEY (plugin Local REST API), "
        "en el entorno o en .claude/obsidian.env.", 3)


def read_content(args):
    if "--file" in args:
        i = args.index("--file")
        return Path(args[i + 1]).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        die("Falta contenido: pásalo por stdin o con --file <archivo>.")
    return sys.stdin.read()


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    vault = get_vault()

    if cmd == "check":
        if isinstance(vault, RestVault):
            info = vault.check()
            print(f"OK {vault.describe()} obsidian={info.get('versions', {}).get('obsidian', '?')}")
        else:
            print(f"OK {vault.describe()} ({len(vault.list())} elementos en la raíz)")
    elif cmd == "read":
        sys.stdout.write(vault.read(args[0]))
    elif cmd == "exists":
        print("yes" if vault.exists(args[0]) else "no")
    elif cmd == "write":
        vault.write(args[0], read_content(args[1:]))
        print(f"Guardado: {clean_path(args[0])}")
    elif cmd == "append":
        vault.append(args[0], read_content(args[1:]))
        print(f"Agregado a: {clean_path(args[0])}")
    elif cmd == "list":
        print("\n".join(vault.list(args[0] if args else "")))
    elif cmd == "search":
        print("\n".join(vault.search(" ".join(args))) or "(sin resultados)")
    else:
        die(f"Comando desconocido: {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
