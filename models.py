from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, username, rol, nume_complet, locatie_id):
        self.id = id
        self.username = username
        self.rol = rol
        self.nume_complet = nume_complet
        self.locatie_id = locatie_id

    def is_admin(self):
        return self.rol == 'admin'

    def is_manager(self):
        return self.rol in ('admin', 'manager')
