# Aspectos legales y comerciales (pendientes antes de cobrar)

Los **pagos no están implementados** a propósito. Los planes (Free, Pro, Elite) existen y se aplican sus límites, pero el
cambio de plan lo hace un administrador. Antes de activar cobros conviene revisar, con asesoramiento profesional:

1. **Naturaleza del servicio**: la plataforma ofrece análisis estadístico, no apuestas. Aun así, en España y en la UE la
   publicidad o promoción vinculada a juego está regulada (Ley 13/2011 de regulación del juego y RD 958/2020 de
   comunicaciones comerciales). Evitar enlaces de afiliación a casas de apuestas, mensajes de "ganancia segura" y dirigirse
   a menores sin revisión legal previa.
2. **Protección del consumidor**: información precontractual clara, derecho de desistimiento de 14 días en servicios
   digitales (con las excepciones aplicables), cancelación tan sencilla como la contratación, precios con impuestos.
3. **Fiscalidad**: IVA de servicios digitales (régimen OSS en la UE) y facturación.
4. **Pasarela**: proveedor que cumpla PSD2/SCA (p. ej. Stripe), sin almacenar datos de tarjeta en nuestros servidores.
5. **Licencias de datos**: confirmar por escrito que el plan contratado con cada proveedor permite mostrar datos (y
   productos derivados como predicciones) a usuarios de pago. Ver [DATA_PROVIDERS.md](DATA_PROVIDERS.md).
6. **RGPD**: política de privacidad, registro de actividades de tratamiento, contratos de encargado con proveedores
   (hosting, email, Sentry), base legal de las notificaciones push y del análisis de uso.
7. **Descargo de responsabilidad** visible: las predicciones son estimaciones y pueden fallar (ya incluido en el registro
   y en cada ficha de partido).

Con todo ello resuelto, la integración de pagos se limita a: webhook de la pasarela → actualizar `users.plan_code`
(el control de acceso por plan ya está implementado y probado).
