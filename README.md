# F1 Calendario 2026

Mini web personal con los horarios de la temporada 2026 de Fórmula 1, siempre en
hora argentina. Incluye cuenta regresiva, estado de cada sesión (pasada, en vivo o
próxima), novedades y manifest para instalarla como app en el celular.

Hecha con HTML, CSS y JavaScript vanilla. Sin frameworks, sin build y sin costo.

## Estructura

```
.
├── index.html                  # Toda la web (HTML + CSS + JS)
├── manifest.json               # Configuración de la app instalable (PWA)
├── sw.js                       # Service worker para instalación y modo offline
├── README-AVISOS.md            # Cómo configurar los avisos por ntfy
├── icons/
│   ├── icon-192.png
│   └── icon-512.png
├── data/
│   ├── temporada-2026.json     # Calendario y horarios en UTC
│   ├── novedades.json          # Novedades con fecha y texto corto
│   ├── posiciones.json         # Tablas de pilotos y constructores
│   └── avisos_enviados.json    # Registro de avisos ya enviados
├── scripts/
│   ├── validar_datos.py        # Validación del JSON antes de publicar
│   ├── avisos.py               # Detección de sesiones y envío por ntfy
│   └── posiciones.py           # Descarga las tablas del campeonato
└── .github/
    └── workflows/
        ├── avisos.yml          # Ejecuta avisos.py cada 5 minutos
        └── posiciones.yml      # Actualiza las tablas los lunes
```

## Ver la web en local

El navegador no permite leer JSON con `file://`, así que hay que levantar un
servidor local:

```bash
cd "F1 CALENDARIO"
python -m http.server 8000
```

Después abrir <http://localhost:8000>.

## Validar los datos

Antes de publicar cambios:

```bash
python scripts/validar_datos.py
```

El script revisa que:

- el JSON sea válido y tenga todas las claves;
- las rondas sean consecutivas y no estén repetidas;
- cada sesión tenga un tipo permitido y una hora ISO 8601 en UTC;
- no haya horas vacías, inválidas ni sesiones desordenadas;
- cada GP tenga clasificación y carrera, y las prácticas correspondientes;
- las novedades tengan fecha y texto.

Si encuentra errores, termina con código 1 (sirve para usarlo en CI).

## Datos y fuentes

- **Todos los horarios se guardan en UTC**, en formato ISO 8601
  (`2026-10-30T18:30:00Z`), y se muestran con `Intl.DateTimeFormat` usando
  `timeZone: 'America/Argentina/Buenos_Aires'`.
- El calendario tiene **23 fechas**: el GP de Arabia Saudita fue cancelado y el
  GP de Baréin se disputó en Sepang (Malasia).
- Los horarios base provienen de [sportstimes/f1](https://github.com/sportstimes/f1)
  (UTC). Las rondas 19 a 23 se contrastaron con la agenda de ESPN y la web
  oficial de F1.
- Cada GP del JSON tiene un campo `fuente` con su página oficial y un campo
  `verificado`. Las rondas 1 a 18 quedaron como `verificado: false` para que se
  puedan contrastar antes de usar los avisos automáticos.
- Los fines de semana con sprint son seis: China, Miami, Canadá, Gran Bretaña,
  Países Bajos y Singapur.

> Los horarios pueden cambiar por decisión de la FIA o del promotor. La web
> enlaza a la fuente oficial de cada fecha.

## Posiciones del campeonato

La sección **Posiciones** de la web lee `data/posiciones.json`, que se genera
con:

```bash
python scripts/posiciones.py
```

El script consulta la API pública de
[Jolpica F1](https://github.com/jolpica/jolpica-f1) (compatible con Ergast),
guarda pilotos y constructores con puntos y victorias, y anota la fecha de
actualización en UTC. Si la consulta falla, deja el archivo anterior intacto y
termina con código 1.

El workflow `.github/workflows/posiciones.yml` lo ejecuta **todos los lunes a
las 12:00 UTC** (09:00 en Argentina) y commitea el JSON solo si cambió. También
se puede correr a mano desde **Actions → Posiciones → Run workflow**.

> Las tablas se actualizan una vez por semana: después de cada carrera pueden
> quedar desactualizadas hasta el lunes siguiente.

## Deploy en GitHub Pages

1. Subir el proyecto a un repositorio de GitHub.
2. Ir a **Settings → Pages**.
3. En **Build and deployment**, elegir **Deploy from a branch**.
4. Seleccionar la rama `main` y la carpeta `/ (root)`.
5. Guardar y esperar a que GitHub publique la URL.

No hace falta build ni configuración extra. Los paths son relativos, así que
funciona tanto en `usuario.github.io/repo/` como en un dominio propio.

### App instalable (PWA)

Con el sitio publicado por HTTPS, en Android/Chrome aparece la opción
**Instalar app** (también se muestra un botón en la portada cuando el navegador
lo permite). En iPhone: **Compartir → Agregar a pantalla de inicio**.

## Variables y secretos

Este repositorio **no contiene** tokens, contraseñas ni direcciones de mail.
Los datos van en **Settings → Secrets and variables → Actions**:

| Nombre | Etapa | Uso |
| --- | --- | --- |
| `NTFY_TOPIC` | 2 | Tema de ntfy donde se publican las notificaciones |
| `NTFY_URL` | 2 | Opcional, si se usa un servidor ntfy propio |
| `MINUTOS_ANTICIPACION` | 2 | Opcional, minutos de anticipación (por defecto 60) |
| `URL_WEB` | 2 | Opcional, link que abre la notificación |
| `GMAIL_USER` | 3 | Cuenta de Gmail que envía el mail |
| `GMAIL_APP_PASSWORD` | 3 | Contraseña de aplicación de Gmail (no la normal) |
| `MAIL_TO` | 3 | Dirección que recibe los avisos |

## Avisos automáticos (Etapa 2)

`scripts/avisos.py` revisa el calendario y manda un push por ntfy cuando una
sesión empieza dentro de los próximos minutos. El workflow
`.github/workflows/avisos.yml` lo ejecuta cada 5 minutos y guarda en
`data/avisos_enviados.json` lo que ya avisó, así no repite notificaciones.

Los pasos para crear el tema, cargar el secreto y probarlo están en
[`README-AVISOS.md`](README-AVISOS.md).

Para probar sin enviar nada:

```bash
python scripts/avisos.py --dry-run
```

La Etapa 3 (aviso por Gmail) queda pendiente.
