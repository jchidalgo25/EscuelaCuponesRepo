---
name: obsidian-vault
description: Guarda y consulta la información de los proyectos en la bóveda de Obsidian del usuario (resumen del proyecto, bitácora de sesiones, decisiones técnicas y pendientes). Úsala cuando el usuario diga "guarda esto en Obsidian", "documenta en mi bóveda", "anota lo que hicimos", "actualiza la bitácora", "registra esta decisión", "qué tengo en Obsidian sobre…", o invoque /obsidian-vault. También al terminar un trabajo importante si el usuario pidió llevar registro en Obsidian.
---

# Bóveda de Obsidian — registro de proyectos

Esta skill conecta Claude con la bóveda de Obsidian para dejar documentado
cada proyecto en el que trabajamos. Todo se hace con el script
`scripts/obsidian.py` (Python 3, sin dependencias).

```bash
OBS="python3 .claude/skills/obsidian-vault/scripts/obsidian.py"
```

## 1. Conexión (hacer siempre primero)

```bash
$OBS check
```

- `OK modo=...` → seguir.
- Código 3 / "no está configurado" → explicarle al usuario las opciones de
  la sección **Configuración** y detenerse. No inventar rutas.
- "No se pudo conectar" → Obsidian cerrado o plugin apagado; avisar al usuario.

## 2. Estructura en la bóveda

Todo va bajo `Proyectos/<Nombre del proyecto>/` (si el usuario ya usa otra
carpeta para proyectos en su bóveda, respétala):

| Nota | Contenido | Cómo se actualiza |
|---|---|---|
| `<Proyecto>.md` | Ficha del proyecto: resumen, stack, estructura, entornos, cómo ejecutarlo | `write` (reescribir completa al cambiar) |
| `<Proyecto> - Bitácora.md` | Una entrada por sesión de trabajo, la más nueva al final | `append` |
| `<Proyecto> - Decisiones.md` | Decisiones técnicas tipo ADR | `append` |
| `<Proyecto> - Pendientes.md` | Checklist `- [ ]` de tareas abiertas | `read` + `write` |

Plantillas en `templates/` (`proyecto.md`, `sesion.md`, `decision.md`,
`pendientes.md`). Reemplaza todos los `{{...}}`; borra secciones que
queden vacías en vez de dejar marcadores.

**Nombre del proyecto:** si el usuario no lo da, usa el nombre del repositorio
(`basename $(git rev-parse --show-toplevel)`), p. ej. `EscuelaCuponesRepo`.
Antes de crear, haz `$OBS list Proyectos` y `$OBS search <nombre>` para
reutilizar la carpeta existente si ya hay una con nombre parecido.

## 3. Flujos

### Registrar el proyecto (primera vez)
1. Revisa el repo (README, package.json, estructura de `src/`, scripts, `git log`).
2. Llena `templates/proyecto.md` con datos reales del código.
3. Escribe la ficha y crea Bitácora/Decisiones/Pendientes si no existen:
   ```bash
   $OBS write "Proyectos/EscuelaCuponesRepo/EscuelaCuponesRepo.md" <<'EOF'
   ...contenido...
   EOF
   ```

### Guardar lo que hicimos en la sesión
1. Reúne: `git log --oneline` de la sesión, `git diff --stat`, rama actual y
   lo conversado.
2. Llena `templates/sesion.md` (fecha `date +%F`) y agrégalo:
   ```bash
   $OBS append "Proyectos/<P>/<P> - Bitácora.md" <<'EOF'
   ...entrada...
   EOF
   ```
3. Si hubo decisiones de arquitectura → `append` a Decisiones.
4. Si quedaron tareas abiertas → `read` Pendientes, agrega/marca `[x]`, `write`.
5. Si cambió el stack, estructura o despliegue → actualiza la ficha y el campo
   `actualizado:` del frontmatter.

### Consultar
```bash
$OBS search "cupones"           # buscar en toda la bóveda
$OBS read "Proyectos/<P>/<P>.md"
$OBS list "Proyectos/<P>"
```
Resume lo encontrado al usuario; no pegues notas enteras si no las pidió.

## 4. Reglas

- **Nunca guardes secretos**: ni contenidos de `.env`, tokens, API keys,
  contraseñas ni URLs con credenciales. Menciona que existe la variable, no su valor.
- No sobrescribas (`write`) Bitácora ni Decisiones: solo `append`.
  Antes de `write` sobre una nota existente, haz `read` y conserva lo que el
  usuario haya escrito a mano.
- Usa wikilinks `[[Nota]]` para enlazar notas del mismo proyecto.
- Escribe en español, conciso y concreto (archivos, comandos, motivos).
- Al terminar, dile al usuario qué notas se crearon/actualizaron (rutas).

## 5. Configuración (para explicársela al usuario)

Las variables pueden ir en el entorno o en `.claude/obsidian.env`
(ignorado por git) o `~/.claude/obsidian.env`:

**Opción A — Plugin Local REST API (recomendado si Obsidian está abierto):**
1. En Obsidian: Ajustes → Complementos de la comunidad → instalar y activar
   **Local REST API**.
2. Copiar la API key que muestra el plugin.
3. ```
   OBSIDIAN_API_URL=https://127.0.0.1:27124
   OBSIDIAN_API_KEY=<tu-api-key>
   ```

**Opción B — Carpeta de la bóveda (no requiere Obsidian abierto):**
```
OBSIDIAN_VAULT_PATH=/ruta/a/MiBoveda
```

**Sesiones en la nube (claude.ai/code):** el contenedor no ve tu PC, así que
ni `127.0.0.1` ni tu carpeta local son accesibles. Opciones:
- Tener la bóveda en un repo Git (plugin *Obsidian Git*), clonarlo en la
  sesión y usar `OBSIDIAN_VAULT_PATH` apuntando al clon; luego commit + push
  del repo de la bóveda.
- Exponer la REST API con un túnel (p. ej. Cloudflare Tunnel/ngrok) y usar esa
  URL en `OBSIDIAN_API_URL`, guardando la key como secreto del entorno.
- O usar la skill desde Claude Code en tu computadora (modo A o B).

`OBSIDIAN_MODE=fs|rest` fuerza un modo si hay ambos configurados.
