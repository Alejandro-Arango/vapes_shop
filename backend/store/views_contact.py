"""
Archivo: views_contact.py
Descripcion: Gestiona el formulario de contacto, registro de leads, notificacion por correo y enlace de WhatsApp.
Dependencias: Django settings, Django mail, Django REST Framework y serializador ContactLeadSerializer
"""

import logging
from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .audit import log_event
from .serializers import ContactLeadSerializer
from .throttles import ContactAnonRateThrottle


logger = logging.getLogger(__name__)


def build_whatsapp_contact(contact_data):
    """
    Nombre: build_whatsapp_contact
    Descripcion: Genera el mensaje y la URL de WhatsApp para continuar la conversacion.
    Retorna: Tupla con URL de WhatsApp y mensaje usado.
    """
    name = contact_data.get("name") or "Visitante"
    email = contact_data["email"]
    phone = contact_data.get("phone") or "No indicado"
    lead_message = contact_data.get("message") or "Quiero recibir informacion sobre productos disponibles."

    message = (
        "Hola, vengo desde Vape Shop.\n"
        f"Nombre: {name}\n"
        f"Correo: {email}\n"
        f"Telefono: {phone}\n"
        f"Mensaje: {lead_message}"
    )
    phone_number = getattr(settings, "CONTACT_WHATSAPP_NUMBER", "573016604375")
    whatsapp_url = f"https://wa.me/{phone_number}?text={quote(message)}"

    return whatsapp_url, message


def notify_contact_lead(lead):
    """
    Nombre: notify_contact_lead
    Descripcion: Envia una notificacion por correo al administrador cuando llega un contacto.
    Retorna: True si Django confirma el envio, false si no se pudo enviar.
    """
    recipient = getattr(settings, "CONTACT_NOTIFICATION_EMAIL", "").strip()

    if not recipient:
        return False

    try:
        sent_count = send_mail(
            subject="Nuevo contacto desde Vape Shop",
            message=(
                "Se recibio un nuevo contacto desde el home.\n\n"
                f"Nombre: {lead.name or 'No indicado'}\n"
                f"Correo: {lead.email}\n"
                f"Telefono: {lead.phone or 'No indicado'}\n"
                f"Mensaje: {lead.message or 'No indicado'}\n"
                f"Estado: {lead.get_status_display()}\n"
                f"Mensaje WhatsApp: {lead.whatsapp_message}\n"
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception as exc:
        logger.warning("No se pudo enviar la notificacion de contacto: %s", exc)
        return False

    return sent_count > 0


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ContactAnonRateThrottle])
def contact(request):
    """
    Nombre: contact
    Descripcion: Guarda el correo, notifica al administrador y devuelve URL para WhatsApp.
    """
    serializer = ContactLeadSerializer(data=request.data)

    if not serializer.is_valid():
        log_event(
            "contact_invalid",
            "Contacto rechazado por validaciones.",
            request=request,
            severity="warning",
            metadata={"errors": serializer.errors},
        )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    whatsapp_url, whatsapp_message = build_whatsapp_contact(
        serializer.validated_data
    )
    lead = serializer.save(whatsapp_message=whatsapp_message)
    email_sent = notify_contact_lead(lead)

    log_event(
        "contact_received",
        "Contacto recibido desde el home.",
        request=request,
        metadata={
            "lead_id": lead.id,
            "status": lead.status,
        },
    )

    if email_sent:
        lead.email_notification_sent = True
        lead.save(update_fields=["email_notification_sent"])
    else:
        log_event(
            "contact_email_not_sent",
            "No se pudo enviar la notificacion de contacto.",
            request=request,
            severity="warning",
            metadata={"lead_id": lead.id},
        )

    return Response(
        {
            "message": "Gracias. Registramos tu correo y abriremos WhatsApp para continuar.",
            "lead_id": lead.id,
            "email_sent": email_sent,
            "whatsapp_url": whatsapp_url,
        },
        status=status.HTTP_201_CREATED,
    )
