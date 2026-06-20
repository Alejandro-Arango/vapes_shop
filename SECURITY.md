# Politica de seguridad

## Versiones soportadas

Se mantiene la ultima version publicada y el codigo de la rama principal.
Las ramas antiguas y despliegues no actualizados no reciben correcciones.

## Reportar una vulnerabilidad

No publiques vulnerabilidades, credenciales, datos personales ni instrucciones
de explotacion en issues o discusiones publicas.

Usa el reporte privado de GitHub:

https://github.com/Alejandro-Arango/vapes_shop/security/advisories/new

Incluye, cuando sea posible:

- componente y version afectados;
- impacto observado;
- pasos minimos para reproducir;
- condiciones necesarias para explotar;
- propuesta de mitigacion;
- datos de contacto para coordinar la divulgacion.

No accedas a datos de otras personas, no alteres pedidos reales, no realices
denegacion de servicio y no mantengas persistencia en sistemas evaluados.

## Tiempos objetivo

- Acuse de recibo: hasta 3 dias habiles.
- Evaluacion inicial y severidad: hasta 7 dias habiles.
- Actualizaciones de estado: al menos cada 14 dias mientras siga abierto.

Los tiempos de correccion dependen de la severidad, disponibilidad de parches y
necesidad de coordinar proveedores. La divulgacion publica debe acordarse
despues de desplegar una correccion o mitigacion.

## Credencial expuesta

Una credencial encontrada en Git debe considerarse comprometida aunque se
elimine en un commit posterior. Primero revocala o rotala, luego investiga el
uso y finalmente decide si es necesario reescribir el historial.
