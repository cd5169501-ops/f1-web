# Avisos de sesiones (Etapa 2)

Un script de Python revisa el calendario cada 5 minutos (con GitHub Actions) y
manda una notificación push por [ntfy](https://ntfy.sh) cuando una sesión está
por empezar. Cada aviso se manda una sola vez.

Archivos de esta etapa:

```
scripts/avisos.py                    # Lógica de detección y envío
data/avisos_enviados.json            # Registro de lo ya avisado
.github/workflows/avisos.yml         # Ejecución automática cada 5 minutos
```

## 1. Crear el tema en ntfy

1. Instalar la app **ntfy** en el celular (Android, iPhone o en el navegador).
2. Elegir un tema con un nombre largo y difícil de adivinar, por ejemplo
   `f1-2026-7k3p9x2m`.
3. Suscribirse a ese tema en la app.

> En el servidor público `ntfy.sh` los temas son abiertos: cualquiera que sepa
> el nombre puede leerlos. No uses el nombre del piloto ni algo obvio. Si querés
> privacidad real, se puede usar un servidor ntfy propio y apuntar `NTFY_URL` ahí.

## 2. Probar en la compu

Desde la carpeta del proyecto:

```bash
# Ver qué avisos se mandarían, sin enviar nada
python scripts/avisos.py --dry-run --ahora 2026-10-31T20:30:00Z

# Enviar de verdad (en PowerShell: $env:NTFY_TOPIC="tu-tema")
export NTFY_TOPIC="f1-2026-7k3p9x2m"
python scripts/avisos.py --ahora 2026-10-31T20:30:00Z
```

`--ahora` sirve para simular otra fecha y no tener que esperar a que empiece una
sesión. Sin `--ahora` usa la hora real.

Si el aviso llega al celular, la Etapa 2 funciona.

## 3. Configurar el secreto en GitHub

1. Subir el proyecto a un repositorio de GitHub.
2. Ir a **Settings → Secrets and variables → Actions**.
3. En **Secrets**, tocar **New repository secret**.
4. Nombre: `NTFY_TOPIC`. Valor: el tema elegido (ej. `f1-2026-7k3p9x2m`).
5. Guardar.

Opcionales (mismos pasos, en **Variables** o **Secrets**):

| Nombre | Para qué |
| --- | --- |
| `NTFY_URL` | Servidor ntfy propio (por defecto `https://ntfy.sh`) |
| `MINUTOS_ANTICIPACION` | Minutos de anticipación (por defecto `60`) |
| `URL_WEB` | Link que se abre al tocar la notificación (la web publicada) |

## 4. Probar el workflow

1. Ir a la pestaña **Actions** del repositorio.
2. Elegir **Avisos de sesiones** y tocar **Run workflow**.
3. Para una prueba sin enviar nada, marcar **Solo mostrar los avisos**.
4. Revisar el resultado en el log.

Después de la primera ejecución real, el workflow va a commitear solo el archivo
`data/avisos_enviados.json` con los avisos que mandó.

## 5. Cómo funciona

- Lee `data/temporada-2026.json` y busca las sesiones que empiezan dentro de los
  próximos `X` minutos.
- Si la sesión no está en `data/avisos_enviados.json`, manda el aviso y la anota.
- La clave de cada aviso es `temporada-ronda-tipo-fechaUTC`, así que cambiar el
  orden del JSON o el texto no genera avisos repetidos.
- El aviso se publica con el endpoint JSON de ntfy, que acepta acentos y
  emojis sin problemas.
- Prioridad: carrera 5, clasificación y sprint 4, el resto 3.

## 6. Problemas frecuentes

- **No llega nada**: revisar que el secreto `NTFY_TOPIC` exista, que el tema de
  la app sea idéntico y que la sesión esté dentro de la ventana de minutos.
- **El cron se atrasa**: GitHub no garantiza la hora exacta; en horas pico puede
  demorar 5 a 15 minutos. Con una ventana de 60 minutos no se pierde ningún
  aviso.
- **El workflow se desactivó**: GitHub pausa los crons después de 60 días sin
  actividad en el repositorio. Se reactiva desde **Actions → Enable workflow**.
- **Error al hacer push**: si la rama está protegida, el bot no puede commitear.
  Desactivar la protección para `github-actions[bot]` o correr el workflow sobre
  una rama sin protección.
- **Quiero volver a probar un aviso**: borrar su entrada de
  `data/avisos_enviados.json` (o vaciar el archivo) y volver a ejecutar.

## Etapa 3 (pendiente)

El envío por Gmail (`smtp.gmail.com`, puerto 465) todavía no está implementado.
Se va a sumar al mismo `avisos.py` con `GMAIL_USER` y `GMAIL_APP_PASSWORD`, y se
va a poder activar o desactivar con `ACTIVAR_NTFY` y `ACTIVAR_GMAIL`.
