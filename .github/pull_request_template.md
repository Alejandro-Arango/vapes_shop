## Resumen

Describe el cambio y su motivo.

## Riesgo y recuperacion

- Riesgo principal:
- Plan de rollback:
- ¿Incluye migraciones? Si aplica, confirma compatibilidad expandir-migrar-contraer:

## Validacion

- [ ] `python manage.py check`
- [ ] `python manage.py makemigrations --check --dry-run`
- [ ] `python manage.py test store`
- [ ] Pruebas operativas relevantes
- [ ] Auditoria de dependencias si cambiaron requisitos

## Seguridad

- [ ] No se agregaron secretos, tokens, datos personales ni archivos `.env`.
- [ ] Los permisos nuevos usan minimo privilegio.
- [ ] Los logs no incluyen cuerpos, credenciales ni parametros sensibles.
- [ ] Los cambios en autenticacion, pagos, checkout, admin o infraestructura
      tienen revision explicita.
