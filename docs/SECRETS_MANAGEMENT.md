# Gestion de secretos

Los secretos nunca se almacenan en Git, imagenes Docker, logs, issues, archivos
de respaldo sin cifrar ni documentación compartida.

## Inventario

| Secreto | Ubicacion autorizada | Alcance minimo | Rotacion |
| --- | --- | --- | --- |
| `DJANGO_SECRET_KEY` | `compose.production.env` protegido en el host | Solo Django | Anual o ante exposicion |
| `MYSQL_PASSWORD` | `compose.production.env` y gestor del proveedor | Base de la aplicacion | Cada 180 dias o ante exposicion |
| `MYSQL_ROOT_PASSWORD` | Gestor del proveedor/host | Administracion MySQL | Cada 180 dias o ante exposicion |
| `DJANGO_EMAIL_HOST_PASSWORD` | `compose.production.env` o gestor SMTP | Solo envio requerido | Cada 180 dias o ante exposicion |
| Token GHCR | Almacen seguro de credenciales Docker del host | Solo `read:packages` | Cada 90 dias |
| `MONITOR_WEBHOOK_URL` | GitHub Actions secret | Solo enviar alertas | Anual o ante exposicion |
| `MONITOR_WEBHOOK_TOKEN` | GitHub Actions secret | Solo endpoint de alertas | Cada 180 dias |
| TOTP y codigos de recuperacion | Gestor de contrasenas fuera del servidor | Una identidad administrativa | Al perder control o cambiar administrador |
| Clave de cifrado de backups externos | Gestor KMS/proveedor | Solo cifrar/descifrar backups | Segun politica del proveedor |

`GITHUB_TOKEN` es efimero y lo entrega GitHub Actions. No debe copiarse a
variables permanentes.

## Alta

1. Generar valores con un generador criptograficamente seguro.
2. Otorgar el alcance minimo.
3. Registrar responsable, fecha de creacion y fecha objetivo de rotacion sin
   copiar el valor secreto.
4. Guardar el secreto solamente en su ubicacion autorizada.
5. Verificar que no aparezca en logs ni en `git status`.

Ejemplo para generar una clave Django:

```powershell
.\backend\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Rotacion

1. Crear la nueva credencial sin revocar todavía la anterior cuando el
   proveedor permita coexistencia.
2. Actualizar el almacén autorizado.
3. Reiniciar o desplegar los servicios consumidores.
4. Verificar `/healthz`, correo, backups y monitoreo.
5. Revocar el valor anterior.
6. Registrar fecha, responsable y resultado.

Cambiar `DJANGO_SECRET_KEY` invalida firmas y enlaces temporales, incluidos
tokens de restablecimiento de contraseña. Planifica una ventana y comunica el
impacto.

## Exposicion

1. Revocar o rotar inmediatamente; borrar el texto de Git no es suficiente.
2. Preservar logs y determinar alcance, periodo y sistemas afectados.
3. Buscar el secreto en historial, artefactos, caches, imágenes y backups.
4. Revisar actividad del proveedor y cuentas relacionadas.
5. Seguir `docs/INCIDENT_RESPONSE.md`.
6. Reescribir historial solo después de revocar y coordinar con todos los
   clones.

## Controles de GitHub

Al publicar la rama principal:

- habilitar secret scanning y push protection cuando estén disponibles;
- habilitar private vulnerability reporting;
- proteger la rama principal contra force-push y borrado;
- exigir pull request y una aprobación;
- exigir revisión de `CODEOWNERS`;
- exigir los checks `Django CI`, `Seguridad de dependencias e imagenes` y
  `Deteccion de secretos`;
- impedir que autores aprueben sus propios cambios sensibles.

La exclusión de Gitleaks para `backend/store/tests.py` afecta únicamente la
regla genérica de claves por las contraseñas ficticias de la suite. Las reglas
específicas de proveedores y claves privadas siguen escaneando ese archivo.
