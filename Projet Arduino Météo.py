import sys
from collections import deque
from threading import Thread
from datetime import datetime, date
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QFrame, QLabel,
    QSplitter, QPushButton, QMenu, QTableWidget, QTableWidgetItem, QStackedWidget, QHeaderView, QGraphicsOpacityEffect
)
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.dates as mdates
import serial

class AnimatedMenu(QMenu):
    """Menu déroulant avec animation de fondu"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QMenu {
                background-color: #222222;
                color: white;
                border: 1px solid #555555;
                font-size: 16px;
                padding: 10px;
                margin: 5px;
            }
            QMenu::item {
                padding: 10px 20px;
            }
            QMenu::item:selected {
                background-color: #4CAF50;
            }
        """)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)

    def showEvent(self, event):
        self.anim.start()
        super().showEvent(event)
        
# Configuration du port série
PORT_UTILISE = '/dev/ttyUSB0'  # Port série utilisé
VITESSE = 115200  # Vitesse de communication en bauds


# Classe de réception de données
class ReceptionDonnees:
    def __init__(self, stations, donnees):
        """Initialise la réception des données depuis le port série."""
        self.stations = stations
        self.donnees = donnees
        self.ser = None
        self.running = True
        self.thread = Thread(target=self.reception, daemon=True)
        self.thread.start()
        self.station4_time = None  # Store the latest time from Station 4

    def reception(self):
        """Lit les données du port série et les stocke dans une structure de données."""
        try:
            self.ser = serial.Serial(PORT_UTILISE, baudrate=VITESSE, timeout=1)
            while self.running:
                data = self.ser.readline()
                if data:  # Si réception de données :
                    try:
                        decoded_data = data.decode('utf-8').strip()
                        dic = self.extraction_val_stations_en_dict(decoded_data)
                        for station, (temps, valeurs) in dic.items():
                            if station in self.stations:
                                # If this is Station 4, update the reference time
                                if station == "Wakanda":  # Assuming "Wakanda" is Station 4
                                    self.station4_time = temps  # Update the reference time
                                # Use the time from Station 4 for all stations
                                current_time = self.station4_time if self.station4_time else temps
                                for i, variable in enumerate(self.stations[station]):
                                    if i < len(valeurs):
                                        self.donnees[station][variable].append((current_time, valeurs[i]))
                                        if len(self.donnees[station][variable]) > 50:
                                            self.donnees[station][variable].popleft()
                    except UnicodeDecodeError:
                        print("Les données ne peuvent pas être décodées")
        except serial.SerialException as e:
            print(f"Erreur de connexion au port série: {e}")
        finally:
            if self.ser:
                self.ser.close()

    def extraction_val_stations_en_dict(self, chaine_carac):
        """Convertit les données reçues en un dictionnaire organisé par station."""
        parts = chaine_carac.split('|')[1:-1]
        dic, station_actuel = {}, []
        for item in parts:
            if item == ' & ':
                if station_actuel:
                    # Le premier élément du dictionnaire est le numéro de la station
                    station_num = int(station_actuel[0])
                    # Association du numéro de la station à son nom
                    station_nom = list(self.stations.keys())[station_num - 1]  # -1 car les indices commencent à 0
                    # Extraction du temps (supposons que le temps est le troisième élément)
                    temps_str = station_actuel[2]  # Exemple : "13:11:16"
                    try:
                        temps = datetime.strptime(temps_str.strip(), "%H:%M:%S").time()
                        # Ajoute la date actuelle pour créer un objet datetime.datetime
                        temps = datetime.combine(date.today(), temps)
                    except (ValueError, AttributeError):
                        print(f"Format de temps invalide : {temps_str}")
                        temps = None
                    # Stockage des données avec le temps
                    dic[station_nom] = (temps, station_actuel[3:])  # Exemple : (13:11:16, [21.64, 46.0])
                station_actuel = []
            else:
                try:
                    # Convertir en float uniquement si c'est une valeur numérique
                    if item.strip().replace('.', '', 1).isdigit():  # Vérifie si c'est un nombre
                        station_actuel.append(float(item))
                    else:
                        station_actuel.append(item.strip())  # Conserve les chaînes de caractères
                except ValueError:
                    print(f"Donnée non valide ignorée: {item}")
        if station_actuel:
            station_num = int(station_actuel[0])
            station_nom = list(self.stations.keys())[station_num - 1]
            temps_str = station_actuel[2]
            try:
                temps = datetime.strptime(temps_str.strip(), "%H:%M:%S").time()
                # Ajoute la date actuelle pour créer un objet datetime.datetime
                temps = datetime.combine(date.today(), temps)
            except (ValueError, AttributeError):
                print(f"Format de temps invalide : {temps_str}")
                temps = None
            dic[station_nom] = (temps, station_actuel[3:])
        return dic

    def stop(self):
        """Arrête le thread de réception des données."""
        self.running = False
        if self.thread.is_alive():
            self.thread.join()


class FenetrePrincipale(QMainWindow):
    def __init__(self):
        """Initialise la fenêtre principale de l'application."""
        super().__init__()
        self.setWindowTitle("Visualisation des Données Météo")
        self.setGeometry(100, 100, 800, 500)
        self.setStyleSheet("background-color: black; color: white;")

        # Widget central et layout principal
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # En-tête
        self.header = QLabel("Station Météo", self)
        self.header.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.header)

        # Widget empilé pour basculer entre les pages
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)

        # Configuration de la page du graphique
        self.page_graphique = QWidget()
        self.setup_page_graphique()
        self.stacked_widget.addWidget(self.page_graphique)

        # Configuration de la page du tableau
        self.page_tableau = QWidget()
        self.setup_page_tableau()
        self.stacked_widget.addWidget(self.page_tableau)

        # Bouton pour basculer entre les pages
        self.btn_switch = QPushButton("Afficher le Tableau")
        self.btn_switch.setStyleSheet("background-color: #4CAF50; color: white; font-size: 16px; padding: 10px; border-radius: 5px;")
        self.btn_switch.clicked.connect(self.basculer_page)
        self.main_layout.addWidget(self.btn_switch)

        # Initialisation des stations et des données
        self.stations = {
            "Rennes": ["Luminosité ☀️"],
            "Guingamp": ["Pression(b) 🌫️", "Oxygène 🌱"],
            "Pouillac": ["Anémomètre 🌬️"],
            "Wakanda": ["Température 🌡️", "Humidité 💧"],
            "Thouars": ["Température 🌡️", "Humidité 💧", "CO2 🏭"],
            "Saint-Leu": ["Particules fines ⚪"],
            "Perpignan": ["Particules fines ⚪", "UV", "Anémomètre 🌬️", "Température 🌡️", "Humidité 💧", "Luminosité ☀️", "Pression 🌫️", "CO2 🏭", "Girou 🌬️", "Pluie 🌧️", "Oxygène 🌱", "COV", "ECO2"],
        }

        self.donnees = {station: {variable: deque(maxlen=50) for variable in variables} for station, variables in self.stations.items()}
        self.active_stations = set(self.stations.keys())

        # Dictionnaire pour stocker les unités de chaque variable
        self.unites = {
            "Température 🌡️": "°C",
            "COV": "dave",
            "Humidité 💧": "%",
            "Pression 🌫️": "Pa",
            "Anémomètre 🌬️": "m/s",
            "Pluie 🌧️": "mm",
            "Luminosité ☀️": "Lux",
            "CO2 �": "ppm",
            "Particules fines ⚪": "ppm",
            "Oxygène 🌱": "%",
            "Pression(b) 🌫️": "bar",
            "Girou 🌬️": "dave",
            "UV": "dave",
            "ECO2": "dave",
        }

        # Initialisation des menus déroulants
        self.checkboxes = {}
        self.initialiser_menu_variables()

        # Configuration des timers
        self.timer_graphique = QTimer()
        self.timer_graphique.timeout.connect(self.maj_graphique)
        self.timer_graphique.start(2000)  # Fréquence de mise à jour du graph

        self.timer_tableau = QTimer()
        self.timer_tableau.timeout.connect(self.maj_tableau)
        self.timer_tableau.start(2000)  # Fréquence de mise à jour du tableau

        # Démarrage de la réception des données
        self.reception_donnees = ReceptionDonnees(self.stations, self.donnees)

    def setup_page_graphique(self):
        """Configure la page du graphique avec un graphique en temps réel et des boutons de contrôle."""
        layout = QVBoxLayout(self.page_graphique)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(0)
        layout.addWidget(self.splitter)

        # Cadre pour le graphique
        self.graph_frame = QFrame()
        self.graph_layout = QVBoxLayout(self.graph_frame)
        plt.style.use('dark_background')
        self.canvas = FigureCanvas(plt.Figure(figsize=(6, 4)))
        self.ax = self.canvas.figure.add_subplot(111)
        self.ax.set_title("Données en Temps Réel", color="white")
        self.ax.set_facecolor("black")
        self.ax.tick_params(colors="white")
        self.graph_layout.addWidget(self.canvas)
        self.splitter.addWidget(self.graph_frame)

        # Cadre pour les boutons de sélection
        self.selection_frame = QFrame()
        self.selection_frame.setStyleSheet("background-color: black; color: white;")
        self.selection_layout = QVBoxLayout(self.selection_frame)
        
        # Bouton pour sélectionner les variables
        self.btn_variables = QPushButton("Sélectionner Variables")
        self.btn_variables.setStyleSheet("""
        QPushButton {
                background-color: #555555; 
                color: white; 
                font-size: 16px; 
                border : none; 
                padding: 10px; 
                border-radius: 18px;}
        
        QPushButton:hover {
                background-color: #666666;
            }
                                        
        QPushButton:pressed {
                background-color: #444444;
            }"""
        ) 
        self.btn_variables.clicked.connect(self.afficher_variables)
        self.selection_layout.addWidget(self.btn_variables)
        
        # Bouton de réinitialisation
        self.btn_reset = QPushButton("Réinitialiser")
        self.btn_reset.setStyleSheet("""
        QPushButton {
                background-color: #FFA500; 
                color: black; 
                font-size: 16px; 
                padding: 10px; 
                border : none;
                border-radius: 18px;}
        
        QPushButton:hover {
                background-color: #FFB733;
            }
                                        
        QPushButton:pressed {
                background-color: #E69500;
            }"""
        )
        self.btn_reset.clicked.connect(self.reinitialiser)
        self.selection_layout.addWidget(self.btn_reset)
        
        # Bouton pour quitter
        self.btn_quitter = QPushButton("Quitter")
        self.btn_quitter.setStyleSheet("""
        QPushButton {
                background-color: #FF0000;
                color: white; 
                font-size: 16px; 
                padding: 10px; 
                border : none;
                border-radius: 18px;}
        
        QPushButton:hover {
                background-color: #FF3333;
            }
                                        
        QPushButton:pressed {
                background-color: #CC0000;
            }"""
        )
        self.btn_quitter.clicked.connect(self.close)
        self.selection_layout.addWidget(self.btn_quitter)
        
        self.splitter.addWidget(self.selection_frame)
        self.splitter.setSizes([500, 250])

    def setup_page_tableau(self):
        """Configure la page du tableau pour afficher les données sous forme de tableau."""
        layout = QVBoxLayout(self.page_tableau)
        self.tableau = QTableWidget()
        self.tableau.setColumnCount(4)  # Ajout d'une colonne pour les unités
        self.tableau.setHorizontalHeaderLabels(["Station", "Variable", "Unité", "Valeur"])

        # Désactiver l'affichage des en-têtes de colonnes et de lignes
        self.tableau.verticalHeader().setVisible(False)  # Masquer les en-têtes de lignes
        self.tableau.horizontalHeader().setVisible(False)  # Masquer les en-têtes de colonnes

        # Style du tableau
        self.tableau.setStyleSheet("""
            QTableWidget {
                background-color: black; 
                color: white; 
                font-size: 14px; 
                gridline-color: #555555;
            } 
            QTableWidget::item {
                padding: 10px; 
                border: 1px solid #555555;
            } 
            QTableWidget::item:selected {
                background-color: #4CAF50; 
                color: white;
            }
        """)

        # Configuration des colonnes
        self.tableau.setAlternatingRowColors(True)
        self.tableau.setStyleSheet("alternate-background-color: #222222; background-color: black; color: white;")
        self.tableau.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tableau.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tableau.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tableau.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tableau.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tableau.setSelectionBehavior(QTableWidget.SelectRows)
        self.tableau.setSelectionMode(QTableWidget.SingleSelection)
        layout.addWidget(self.tableau)

    def initialiser_menu_variables(self):
        """Initialise le menu déroulant pour sélectionner les variables."""
        self.menu_variables = AnimatedMenu(self)
        self.checkboxes = {}  # Dictionnaire pour suivre les cases à cocher
        
        green_pixmap = QPixmap(16, 16)
        green_pixmap.fill(QColor("#00C853"))
        icon_green = QIcon(green_pixmap)

        for station, variables in self.stations.items():
            station_menu = self.menu_variables.addMenu(station)
            station_menu.setStyleSheet("""
                QMenu {
                    background-color: #222222;
                    color: white;
                    font-size: 16px;
                    padding: 8px;
                }
                QMenu::item {
                    padding: 10px 20px;
                }
                QMenu::item:selected {
                    background-color: #4CAF50;
                }
            """)
            
            self.checkboxes[station] = {}  # Initialise le dictionnaire pour cette station
            
            for variable in variables:
                action = QAction(variable, self, checkable=True)
                action.setIcon(QIcon())
                action.toggled.connect(lambda checked, a=action: a.setIcon(icon_green if checked else QIcon()))
                station_menu.addAction(action)
                self.checkboxes[station][variable] = action  # Stocke la référence à l'action

    def basculer_page(self):
        """Bascule entre la page du graphique et celle du tableau."""
        if self.stacked_widget.currentIndex() == 0:
            self.stacked_widget.setCurrentIndex(1)
            self.btn_switch.setText("Afficher le Graphique")
        else:
            self.stacked_widget.setCurrentIndex(0)
            self.btn_switch.setText("Afficher le Tableau")

    def afficher_variables(self):
        """Affiche le menu déroulant pour sélectionner les variables."""
        self.menu_variables.exec(self.btn_variables.mapToGlobal(self.btn_variables.rect().bottomLeft()))

    def maj_graphique(self):
        """Met à jour le graphique avec les dernières données disponibles."""
        self.ax.clear()
        self.ax.grid(True, which='both', axis='both', color='white', linestyle='--', linewidth=0.5)
        has_data = False
        
        # Parcourir toutes les stations et variables
        for station, variables in self.checkboxes.items():
            for variable, action in variables.items():
                if action.isChecked():
                    if len(self.donnees[station][variable]) > 0:
                        # Use the time from Station 4 for all stations
                        temps = [t for t, _ in self.donnees[station][variable]]
                        valeurs = [v for _, v in self.donnees[station][variable]]
                        self.ax.plot(temps, valeurs, label=f"{station} - {variable}")
                        has_data = True
        
        if not has_data:
            self.ax.text(0.5, 0.5, "Aucune donnée disponible", color="white", ha="center", va="center", transform=self.ax.transAxes)
        else:
            self.ax.set_title("Données en Temps Réel", color="white")
            # Formate l'axe des temps
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            self.ax.xaxis.set_major_locator(mdates.SecondLocator(interval=10))  # Affiche une étiquette toutes les 10 secondes
            self.ax.legend()
        
        self.canvas.draw()

    def maj_tableau(self):
        """Met à jour le tableau avec les dernières données disponibles, en ordre de station et variable."""
        self.tableau.setRowCount(0)  # On commence par vider le tableau

        # Tri des stations
        stations_triees = list(self.stations.keys())  # Garde l'ordre original

        for station in stations_triees:
            # Ajout d'une ligne pour le nom de la station avec un fond plus sombre
            row = self.tableau.rowCount()
            self.tableau.insertRow(row)
            station_item = QTableWidgetItem(station)
            station_item.setBackground(Qt.darkGray)
            station_item.setForeground(Qt.white)
            station_item.setTextAlignment(Qt.AlignCenter)
            self.tableau.setItem(row, 0, station_item)
            self.tableau.setSpan(row, 0, 1, 4)  # Fusionne la ligne pour la station

            # Tri des variables
            variables_triees = self.stations[station]  # Pas de tri erroné
            for variable in variables_triees:
                row = self.tableau.rowCount()
                self.tableau.insertRow(row)
                self.tableau.setItem(row, 1, QTableWidgetItem(variable))
                self.tableau.setItem(row, 2, QTableWidgetItem(self.unites.get(variable, "N/A")))

                # Ajout de la dernière valeur disponible sans coloration conditionnelle
                dernieres_valeurs = self.donnees[station][variable]
                valeur = dernieres_valeurs[-1][1] if dernieres_valeurs else "N/A"  # Prend la valeur (temps, valeur)
                valeur_item = QTableWidgetItem(str(valeur))
                self.tableau.setItem(row, 3, valeur_item)

        # Ajustement des tailles et styles
        self.tableau.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tableau.setStyleSheet("border: 1px solid #444; alternate-background-color: #222;")

    def reinitialiser(self):
        """Réinitialise toutes les sélections des variables."""
        for station_actions in self.checkboxes.values():
            for action in station_actions.values():
                action.setChecked(False)
        self.maj_graphique()
        self.maj_tableau()

    def closeEvent(self, event):
        """Arrête la réception des données et ferme l'application."""
        self.reception_donnees.stop()
        event.accept()


# Lancement de l'application
app = QApplication(sys.argv)
window = FenetrePrincipale()
window.show()
sys.exit(app.exec())