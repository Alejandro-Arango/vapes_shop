"""
Archivo: admin.py
Descripcion: Define el sitio administrativo protegido por segundo factor.
Dependencias: django-otp
"""

from django_otp.admin import OTPAdminSite


class StoreOTPAdminSite(OTPAdminSite):
    """
    Nombre: StoreOTPAdminSite
    Descripcion: Exige un dispositivo OTP verificado para acceder al panel.
    """

    site_header = "Administracion Vape Shop"
    site_title = "Vape Shop Admin"
    index_title = "Operacion de la tienda"

    def __init__(self, name="admin"):
        super().__init__(name)
