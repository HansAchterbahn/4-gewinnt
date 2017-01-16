### Vier Gewinnt Spiel
### Ansteuerung einer 6x7 LED-Matrix

#------------------------------------------------------------------------#
#                                 HEAD                                   #
#------------------------------------------------------------------------#
### Bibliotheken
import RPi.GPIO as GPIO # Raspberry Pi Standart GPIO Bibliothek
import time             # Bibliothek fuer time-Funktionen
import sys              # This module provides a number of functions and variables that can
                        # be used to manipulate different parts of the Python runtime environment (z.B. sys.exit())

### Initialisierung
GPIO.setmode(GPIO.BCM)  # Verwendung der Pinnamen, wie sie auf dem Board heissen
GPIO.setwarnings(False) # Deaktiviere GPIO-Warnungen
GPIO.cleanup()          # Zuruecksetzen aller GPIO-Pins

G_NOT         = 14      # Output Enable                 OUTPUT
RCK           = 15      # Storage Register Clock        OUTPUT
SCK           = 18      # Shift Register Clock          OUTPUT
SCLR_NOT      = 23      # Shift Register Clear          OUTPUT
SI            = 24      # Serial Data                   OUTPUT
BUTTON_LEFT   = 4       # Button Links                  INPUT
BUTTON_ENTER  = 3       # Button Enter                  INPUT
BUTTON_RIGHT  = 2       # Button Rechts                 INPUT



### Setup GPIOs (Declare GPIOs as INPUT or OUTPUT)
# WICHTIG: Da mit PULL-UP-Widerstand gearbeitet wird, muss der Button den PIN auf LOW ziehen
#          -> Durch Buttondruck wird Pin auf GND gelegt! -> HIGH-Signal in Python
GPIO.setup(G_NOT,GPIO.OUT)                   # OUTPUT
GPIO.setup(RCK,GPIO.OUT)                     # OUTPUT
GPIO.setup(SCK,GPIO.OUT)                     # OUTPUT
GPIO.setup(SCLR_NOT,GPIO.OUT)                # OUTPUT
GPIO.setup(SI,GPIO.OUT)                      # OUTPUT
GPIO.setup(BUTTON_LEFT,GPIO.IN,GPIO.PUD_UP)  # BUTTON_LEFT  -> IN (mit Pull-Up Wiederstand, standartmaessig auf HIGH)
GPIO.setup(BUTTON_ENTER,GPIO.IN,GPIO.PUD_UP) # BUTTON_ENTER -> IN (mit Pull-Up Wiederstand, standartmaessig auf HIGH)
GPIO.setup(BUTTON_RIGHT,GPIO.IN,GPIO.PUD_UP) # BUTTON_RIGHT -> IN (mit Pull-Up Wiederstand, standartmaessig auf HIGH)


### Globale Variablen
# Innerhalb einer Funktion koennen globale Variablen lesend aufgerufen werden
# Will man eine globale Variable innerhalb einer Funktion veraendern,
# muss man diese mit "global ..." in der Funktion definieren!
# Eine innerhalb einer Funktion definierte Variable ist immer lokal
reset               = 0
button_state        = 0                 # Variable fuer Button-Funktion (siehe 'def Button(button_nr)')
button_old          = 0                 # Variable fuer Button-Funktion (siehe 'def Button(button_nr)')
columns             = 14                # 7 Spalten mit jeweils zwei Farben -> 14 (eigentlich 16, da Scheiberegister 16 Bits braucht, letzten 2 Bits sind beliebig und werden in der Funktion send_data() seperat mitgesendet)
columns_unused      = [0,0]             # Anzahl der unbenutzten Spalten (=Anzahl der im Schieberegisterbaustein NICHT benutzten Ausgaenge, HIGH-SIDE)
rows                = 6                 # 6 Zeilen (eigentlich 8, da Schieberegister 8 Bit braucht, letzten 2 Bits sind beliebig und werden in der Funktion send_data() seperat mitgesendet)
rows_unused         = [0,0]             # Anzahl der unbenutzten Zeilen (=Anzahl der im Schieberegisterbaustein nicht benutzten Ausgaenge, LOW-SIDE)
clk_delay           = 0.00000001        # Delay zur sicheren Erkennung der Signalflanken (siehe Datenblatt Schieberegister 74HC595), mind. 6ns
data                = [0]               # Datenvektor mit den aktuellen Daten des Spielfeldes, Initialwert
row                 =  [1,0,0,0,0,0,    # Zeile1
                        0,1,0,0,0,0,    # Zeile2
                        0,0,1,0,0,0,    # Zeile3
                        0,0,0,1,0,0,   	# Zeile4
                        0,0,0,0,1,0,    # Zeile5
                        0,0,0,0,0,1]	# Zeile6
pos                 = 0             	# aktuelle Position in der Matrix (im Datenverktor -> pos = Index des Datenvektors data)
pos_max             = 12            	# maximale Position in einer Zeile (fuer gruen, rot gilt pos_max+1)
player_nr           = 0               	# Player Number (0...Player 1, 1...Player 2)
win_row             = [0,0,0,0]         # Initialwert des Gewinnvekors -> Vektor, der die Positionen der zum Sieg fuehrenden Daten speichert, also Positionen der '4 in einer Reihe'

#------------------------------------------------------------------------#
#                                 Functions                              #
#------------------------------------------------------------------------#
def Button(button_nr):
    #Funktion gibt ein Signal button_state aus, wenn der geforderte Taster gedrueckt wird"
    #Dieses Signal kann nur ausgegeben werden, wenn button_state zuvor 0 war"
    #-> dadurch werden wiederholte Aufrufe der Funktion bei laenger betaetigtem Taster vermieden"
    global button_state
    global button_old

    # Setze button_state auf 1, wenn BUTTON gedrueckt (GPIO.input == 0 wegen Pull-Up) und button_state == 0
    if GPIO.input(button_nr) == 0 and button_state == 0:
        button_old = button_nr                              # Merke aktuelle button_nr
        button_state = 1                                    # Setze button_state auf 1
        time.sleep(0.01)                                    # Zeitverzoegerung, um Tasterprellen zu umgehen
        return button_state                                 # Gib den Wert button_state zurueck

    # Setze button_state auf 0, sobald zuvor betaetigte BUTTON (button_old) losgelassen wird
    elif GPIO.input(button_nr) == 1 and button_state ==1 and button_old == button_nr :
        button_state = 0                                    # Diese elif-Anweisung verhindert, dass der Taster bei durchgehendem Druecken neu ausgeloest wird
        time.sleep(0.01)                                    # Zeitverzoegerung, um Tasterprellen zu umgehen
                                                            # Erfolgt kein Return-Befehlt, liefert die Funktion den Wert 'none'

def Send_Data(data):
    # Funktion sendet 'data' an Shift-Register und aktiviert Ausgabe an das Storage-Register
    # ->Ausgabe der Daten im Storgage-Register auf die LED-Matrix
    # Dabei wird jede Zeile seperat angesteuert
    # -> Immer nur eine Zeile der LED-Matrix wird beschrieben, danach wird diese geloescht und die naechste Zeile beschrieben
    r=0                                 # Zaehlvariable zum Auswaehlen der einzelnen Zeilen im Vektor 'data' und 'row'

    # Schleife sendet (6+2)-Bit-Vektor 'row' mit Information, welche Zeile angesteuert werden soll
    # und (14+2)-Bit-Vektor 'data' mit Information, was in der entsprechenden Zeile angezeigt werden soll
    # (welche LEDs in der entsprechenden Zeile leuchten sollen)
    while r < rows:
        Clear_Shift_Register()                                          # Funktionsaufruf, loesche alle Werte im Shift-Register
        Set_Shift_Register(row[0+r*rows:rows+r*rows])                   # Funktionsaufruf, sende 6-Bit-Vektor 'row' mit Information, welche Zeile angesteuert werden soll
        Set_Shift_Register(rows_unused)                                 # Vektor [0,0] fuer die NICHT benutzten Ausgaenge der Schieberegister HIGH-Side
        Set_Shift_Register(data[0+r*columns:columns+r*columns])         # Funktionsaufruf, sende 14-Bit-Vektor 'data' mit Information, was in der entsprechenden Zeile angezeigt werden soll
        Set_Shift_Register(columns_unused)                              # Vektor [0,0] fuer die NICHT benutzten Ausgaenge der Schieberegister LOW-Side
        Set_Storage_Register()                                          # Funktionsaufruf, Ausgabe der Daten im Shift-Register an LED-Matrix
        r=r+1

def Output_Enable():
    # Funktion aktiviert Ausgaenge der Scheiberegisterbausteine
    GPIO.output(G_NOT,GPIO.LOW)         # Qa bis Qh aktivieren
    time.sleep(clk_delay)               # Delay zur sicheren Erkennung der Signalpegel

def Output_Disable():
    # Funktion deaktiviert Ausgaenge der Scheiberegisterbausteine
    GPIO.output(G_NOT,GPIO.HIGH)        # Qa bis Qh deaktivieren
    time.sleep(clk_delay)               # Delay zur sicheren Erkennung der Signalpegel

def Clear_Shift_Register():
    # Funktion loescht Daten im Shift-Register
    GPIO.output(SCLR_NOT,GPIO.LOW)      # Shift-Register loeschen (solange SCLR_NOT LOW ist)
    time.sleep(clk_delay)
    GPIO.output(SCLR_NOT,GPIO.HIGH)     # Shift-Register wird nichtmehr geloescht
    time.sleep(clk_delay)


def Set_Shift_Register(data):
    # Funktion senden 'data' an Shift-Register
    i=0                                     # Zaehlvariable, Index -> data[i]
    data_length = len(data)                 # Laenge des Datenvektors bestimmen

    while i < data_length:
        # Hier wird geschaut ob das aktuell zu uebergebende Bit 1 oder 0 ist
        if data[i] == 1:
            GPIO.output(SI,GPIO.HIGH)       # Wenn data[i] == 1 -> SERIAL DATA OUTPUT 'SI'auf HIGH
            time.sleep(clk_delay)
        elif data[i] == 0:
            GPIO.output(SI,GPIO.LOW)        # Wenn data[i] == 0 -> SERIAL DATA OUTPUT 'SI' auf LOW
            time.sleep(clk_delay)


        GPIO.output(SCK,GPIO.HIGH)  # Uebergabe des Serial Data Wertes in erste Stufe des Shift-Registers
        time.sleep(clk_delay)       # und Weitergabe der aktuellen Werte des Shiftregisters einer Stufe
        GPIO.output(SCK,GPIO.LOW)   # auf die Naechste bei LOW-HIGH-Flanke
        time.sleep(clk_delay)

        i=i+1


def Set_Storage_Register():
    # Funktion gibt aktuellen Daten im Shift-Register an Storage-Register weiter bei LOW-HIGH-Flanke an RCK
    # (Das Storage-Register (=Ausgang) gibt Daten direkt auf die LED-Matrix bzw. die Treiberstufen vor der Matrix,
    # sofern die Ausgaenge Qa bis Qh der Schieberegisterbausteine aktiviert wurden (siehe 'def Output_Enable()')
    GPIO.output(RCK,GPIO.HIGH)
    time.sleep(clk_delay)
    GPIO.output(RCK,GPIO.LOW)
    time.sleep(clk_delay)


def Sample(sample_nr):
    # Funktion enthaelt verschiedene Samples, welche mithilfe der Funktion Send_Data() auf der LED-Matrix
    # angezeigt werden koennen, z.B.: Send_Data(Sample(2))
    # WICHTIG: Die LED-Matrix besitzt nur 7 LED-Spalten mit je 2 Farben (gruen(g), rot(r)) -> 14 Spalten
    #          Da die Schieberegisterbausteine zur Ansteuerung der Spalten aber 2*8=16 Ausgaenge besitzen,
    #          muessen die 2 ungenutzten Ausgaenge (Spalte 15 und 16) mitgesendet werden
    #          Diese werden in der Funktion send_data() seperat mitgesendet und muessen hier nit extra eingetragen werden

    if sample_nr == 0: 				 # Startbildschirm
            #  |LD1|LD2|LD3|LD4|LD5|LD6|LD7|
            #  |g,r|g,r|g,r|g,r|g,r|g,r|g,r|
        data = [1,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile1
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile2
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile3
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile4
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile5
                0,0,0,0,0,0,0,0,0,0,0,0,0,0]     # Zeile6

    if sample_nr == 1:                           # "HI"
            #  |LD1|LD2|LD3|LD4|LD5|LD6|LD7|
            #  |g,r|g,r|g,r|g,r|g,r|g,r|g,r|
        data = [0,1,0,0,0,0,0,1,0,0,1,0,1,0,     # Zeile1
                0,1,0,0,0,0,0,1,0,0,1,0,1,0,     # Zeile2
                0,1,0,1,0,1,0,1,0,0,1,0,1,0,     # Zeile3
                0,1,0,0,0,0,0,1,0,0,1,0,1,0,     # Zeile4
                0,1,0,0,0,0,0,1,0,0,1,0,1,0,     # Zeile5
                0,1,0,0,0,0,0,1,0,0,1,0,1,0]     # Zeile6

    if sample_nr == 2:                           # "DU"
            #  |LD1|LD2|LD3|LD4|LD5|LD6|LD7|
            #  |g,r|g,r|g,r|g,r|g,r|g,r|g,r|
        data = [1,0,1,0,0,0,0,0,0,1,0,0,0,1,     # Zeile1
                1,0,0,0,1,0,0,0,0,1,0,0,0,1,     # Zeile2
                1,0,0,0,1,0,0,0,0,1,0,0,0,1,     # Zeile3
                1,0,0,0,1,0,0,0,0,1,0,0,0,1,     # Zeile4
                1,0,0,0,1,0,0,0,0,1,0,0,0,1,     # Zeile5
                1,0,1,0,0,0,0,0,0,1,0,1,0,1]     # Zeile6

    if sample_nr == 3:                           # Spieler 1 gewinnt
            #  |LD1|LD2|LD3|LD4|LD5|LD6|LD7|
            #  |g,r|g,r|g,r|g,r|g,r|g,r|g,r|
        data = [1,0,1,0,0,0,0,0,0,0,0,0,1,0,     # Zeile1
                1,0,0,0,1,0,0,0,0,0,1,0,1,0,     # Zeile2
                1,0,1,0,0,0,0,0,1,0,0,0,1,0,     # Zeile3
                1,0,0,0,0,0,0,0,0,0,0,0,1,0,     # Zeile4
                1,0,0,0,0,0,0,0,0,0,0,0,1,0,     # Zeile5
                0,0,0,0,0,0,0,0,0,0,0,0,0,0]     # Zeile6

    if sample_nr == 4:                           # Spieler 2 gewinnt
            #  |LD1|LD2|LD3|LD4|LD5|LD6|LD7|
            #  |g,r|g,r|g,r|g,r|g,r|g,r|g,r|
        data = [0,1,0,1,0,0,0,0,0,1,0,1,0,1,     # Zeile1
                0,1,0,0,0,1,0,0,0,0,0,0,0,1,     # Zeile2
                0,1,0,1,0,0,0,0,0,1,0,1,0,1,     # Zeile3
                0,1,0,0,0,0,0,0,0,1,0,0,0,0,     # Zeile4
                0,1,0,0,0,0,0,0,0,1,0,1,0,1,     # Zeile5
                0,0,0,0,0,0,0,0,0,0,0,0,0,0]     # Zeile6

    if sample_nr == 5: 				 # Unentschieden
            #  |LD1|LD2|LD3|LD4|LD5|LD6|LD7|
            #  |g,r|g,r|g,r|g,r|g,r|g,r|g,r|
        data = [1,0,1,0,1,0,1,0,1,0,1,0,1,0,     # Zeile1
                1,0,0,1,0,1,0,0,0,1,0,1,1,0,     # Zeile2
                1,0,0,0,0,0,0,1,0,0,0,0,1,0,     # Zeile3
                1,0,0,0,0,0,0,1,0,0,0,0,1,0,     # Zeile4
                1,0,0,1,0,1,0,0,0,1,0,1,1,0,     # Zeile5
                1,0,1,0,1,0,1,0,1,0,1,0,1,0]     # Zeile6

    if sample_nr == 6:                           # Lauftext, Player 2 Win
            #  |LD1|LD2|LD3|LD4|LD5|LD6|LD7|  -->                                                                              |LD1|LD2|LD3|LD4|LD5|LD6|LD7|
            #  |g,r|g,r|g,r|g,r|g,r|g,r|g,r|  -->                                                                              |g,r|g,r|g,r|g,r|g,r|g,r|g,r|
        data = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,1,0,0,0,0,0,1,0,1,0,1,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile1
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile2
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,1,0,0,0,0,0,1,0,1,0,1,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0,1,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile3
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile4
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1,0,1,0,1,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile5
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]     # Zeile6

    if sample_nr == 7:                           # Lauftext, Start-Screen '4 GEWINNT'
            #  |LD1|LD2|LD3|LD4|LD5|LD6|LD7|  -->     																                                          								   |LD1|LD2|LD3|LD4|LD5|LD6|LD7|
            #  |g,r|g,r|g,r|g,r|g,r|g,r|g,r|  -->                                                                                                                         	                   |g,r|g,r|g,r|g,r|g,r|g,r|g,r|
        data = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,1,0,1,0,1,0,0,0,1,0,1,0,1,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,1,0,1,0,1,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile1
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile2
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,1,0,1,0,0,0,0,0,1,0,0,0,1,0,1,0,0,0,1,0,1,0,1,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0,1,0,0,0,1,0,0,0,1,0,1,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile3
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0,1,0,0,0,1,0,0,0,1,0,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile4
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,1,0,1,0,1,0,1,0,0,0,1,0,1,0,1,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,     # Zeile5
                0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]     # Zeile6

    return(data)            # Funktion gibt bei Aufruf als Wert den Vektor 'data' zuruek

def Position_Check(level):
    # Funktion zur Ueberpruefung, ob auf der aktuellen Position in der Matrix eine 1 oder eine 0 ist
    # Je nach player_nr wird auch geprueft, ob die rechte oder linke Position der aktuellen 1 oder 0 ist
    # Dies ist wichtig, da sonst in einer LED beide Farben leuchten koennen
    # ->|LD1|
    #   |g,r|
    #   |1,1|
    state = data[pos]==level or (data[pos+1]==level and player_nr==0) or (data[pos-1]==level and player_nr==1)

    return(state)           # Funktion gibt bei Aufruf 'state' (1 oder 0) zuruek

def Win_Check(r):
    # Funktion ueberprueft, ob sich horizontal, vertikal oder diagonal "4 in einer Reihe" befinden
    # Dazu wird ausgehend von der aktuellen Position in allen Richtungen gesucht
    # und die Variable 'coins_in_a_row' hochgezaehlt
    # Sobald diese den Wert 4 erreicht, endet die Funktion und gibt den Wert '1' zurueck
    # Sollten keine 4 in einer Reihe gefunden werden, endet die Funktion ohne Rueckgabewert
    # "4 in einer Reihe" entspricht 4 LEDs der gleichen Farbe in einer Reihe (horizontal, vertikal oder diagonal) auf der LED-Anzeige
    global win_row

    i=1                                         # Zaehlvariable zum aendern der Position horizontal, vertikal oder diagonal
    coins_in_a_row = 1                          # Zaehler fuer Anzahl der LEDs in einer Reihe (horizontal, vertikal oder diagonal)
    r=rows-r-1                                  # r ...in welcher Zeile befinde ich mich aktuell
    x_max = r*columns + pos_max+player_nr       # Abfragegrenze (rechter Rand der Matrix) in x-Richtung
    x_min = r*columns + player_nr               # Abfragegrenze (linkter Rand der Matrix) in x-Richtung
    win_row = [pos,0,0,0]                       # Speichert die Positionen der LEDs in der Gewinn-Reihe (fuer Blinkende Hervorhebung der Gewinnreihe aud Anzeige)


    #Horizontal nach rechts					  			# |0 0 0 0 0 0|
    while pos+i*2<=x_max:								# |0 0 0 0 0 0|
        if data[pos+i*2]==1:							# |0 0 0 0 0 0|
            win_row[coins_in_a_row]=pos+i*2     		# |0 x x x x 0|
            coins_in_a_row=coins_in_a_row+1
            if coins_in_a_row==4:
                return(1)
            i=i+1
        else:
            break
    i=1
    #Horizontal nach links
    while pos-i*2>=x_min:
        if data[pos-i*2]==1:
            win_row[coins_in_a_row]=pos-i*2
            coins_in_a_row=coins_in_a_row+1
            if coins_in_a_row==4:
                return(1)
            i=i+1
        else:
            break


    i=1
    coins_in_a_row=1
    #Vertikal nach unten								# |0 x 0 0 0 0|
    while pos+i*columns<rows*columns:		    		# |0 x 0 0 0 0|
        if data[pos+i*columns]==1:						# |0 x 0 0 0 0|
            win_row[coins_in_a_row]=pos+i*columns   	# |0 x 0 0 0 0|
            coins_in_a_row=coins_in_a_row+1
            if coins_in_a_row==4:
                return(1)
            i=i+1
        else:
            break


    i=1
    coins_in_a_row=1
    #Diagonal nach rechts steigend   			      	# |0 0 0 0 x 0|
    while pos-i*columns>0 and pos+i*2<=x_max:           # |0 0 0 x 0 0|
        if data[pos+i*2-i*columns]==1:                  # |0 0 x 0 0 0|
            win_row[coins_in_a_row]=pos+i*2-i*columns   # |0 x 0 0 0 0|
            coins_in_a_row=coins_in_a_row+1
            if coins_in_a_row==4:
                return(1)
            i=i+1
        else:
            break
    i=1
    #Diagonal nach links fallend
    while pos+i*columns<rows*columns and pos-i*2>=x_min:
        if data[pos-i*2+i*columns]==1:
            win_row[coins_in_a_row]=pos-i*2+i*columns
            coins_in_a_row=coins_in_a_row+1
            if coins_in_a_row==4:
                return(1)
            i=i+1
        else:
            break


    i=1
    coins_in_a_row=1
    #Diagonal nach rechts fallend 										# |0 x 0 0 0 0|
    while pos+i*columns<rows*columns and pos+i*2<=x_max:                # |0 0 x 0 0 0|
        if data[pos+i*2+i*columns]==1:                                  # |0 0 0 x 0 0|
            win_row[coins_in_a_row]=pos+i*2+i*columns                   # |0 0 0 0 x 0|
            coins_in_a_row=coins_in_a_row+1
            if coins_in_a_row==4:
                return(1)
            i=i+1
        else:
            break
    i=1
    #Diagonal nach links steigend
    while pos-i*columns>0 and pos-i*2>=x_min:
        if data[pos-i*2-i*columns]==1:
            win_row[coins_in_a_row]=pos-i*2-i*columns
            coins_in_a_row=coins_in_a_row+1
            if coins_in_a_row==4:
                return(1)
            i=i+1
        else:
            break

def Win_Screen():
    # Funktion zeigt die "4 in einer Reihe" des Gewinners 10s im Blinkinterval von 0.25s an
    # und ruft danach fuer 4s eine blinkende Gewinnanzeige (Sample(3+player_nr)) mit der Spielernummer des Gewinner
    # im 0.5s Blinkintervall auf

    # For-Schleife zur blinkenden Hervorhebung der Gewinnreihe
    # Dabei wird fuer 10*0.25s = 2,5s das Spielfeld angezeigt
    # und alle 0.25s die Gewinnreihe ein- und ausgeschaltet
    for x in range (0, 9):                      # Von x=0 bis 9
        Blink_Screen(0.25, 0, data)                 # Gib aktuelles Spielfeld aus
        for i in range (0, 4):                      # Von i=0 bis 4
            data[win_row[i]] = not data[win_row[i]]     # Toogle Data der Gewinnreihe => Gewinnreihe auf 1 bzw. 0 setzen

    Blink_Screen(4, 0.5, Sample(3+player_nr))   # Ausgabe der Spielernummer des Gewinners fuer 4s im 0.5s Blinkintervall


def Draw_Screen():
    # Funktion ruft fuer 4sec eine blinkende Unentschiedenanzeige (Sample(5))
    # mit 0.5sec Blinkintervall auf
    Blink_Screen(4, 0.5, Sample(5))


def Blink_Screen(time_length, interval, data):
    # Funktion schreibt "data" auf die Matrix und laesst diese fuer die angegebene Dauer 'time_length'
    # im entsprechenden Intervall 'interval' blinken
    # Dabei werden die Ausgaenge der Schieberegister im entsprechenden Takt aktiviert und deaktiviert
    # Angaben der Zeitwerte in sec
    # time.time(): Return the time in seconds since the epoch as a floating point number from the system clock.

    time_start = time.time()    	# Schreibe die aktuelle Systemzeit auf die Variable 'time_start'
    time_start_blink = time.time()	# Schreibe die aktuelle Systemzeit auf die Variable 'time_start_blink'

    while time.time() < time_start + time_length:   # Solange aktuelle Systemzeit die Startsystemzeit + die geforderte Zeit, die die Matrix blinken soll, nicht ueberschritten hat:
        Send_Data(data)				    	# Sende Daten
	# Durch die If-Schleife wird der Ausgang der Schieberegister in geforderten Intervall Ein- und Ausgeschaltet
        if time.time() > time_start_blink + interval: 	# Sobald aktuelle Systemzeit die Start-Blink-Zeit + die Blink-Intervall-Zeit ueberschritten hat:
            Output_Disable()				# Deaktiviere Ausgang der Schieberegister
            time.sleep(interval) 			# Schlafe fuer die Dauer des Blink-Intervalls
            Output_Enable()					# Aktiviere Ausgang der Schieberegister
            time_start_blink = time.time()	# Setze time_start_blink erneut auf die aktuelle Systemzeit


def Send_Running_Text(text):
    # Funktion sendet eine Lauftext (Textsample, welches laenger als die breite des Displays ist) auf das Display
    # Dabei wird der Text von rechts nach links ueber die Anzeige geschoben, sodass ein bewegtes Bild entsteht
    # Um den Lauftext zu erzeugen, wird nur ein Ausschnitt des gesammten Datenvektors 'text' genommen
    # Dieser wird an den Vektor 'data' uebergeben und fuer 0.15s durch die Funktion Blink_Screen() dargestellt
    # Danach wird der aktuelle Ausschnitt des Datenvektors 'text' um eine Spalte nach rechts verschoben
    # Nun wird auch dieser an den Vektor 'data' uebergeben und fuer 0.15s durch die Funktion Blink_Screen() dargestellt
    # -> solange, bis der Ausschnitt des Datenvektors 'text' die letze Spalte erreicht

    #  |LD1|LD2|LD3|LD4|LD5|LD6|LD7|     -->       |LD1|LD2|LD3|LD4|LD5|LD6|LD7|
    #  |g,r|g,r|g,r|g,r|g,r|g,r|g,r|     -->       |g,r|g,r|g,r|g,r|g,r|g,r|g,r|
    #  -----------------------------               ----------------------------
    #  |0,1,0,0,0,1,0,0,0,0,0,1,0,1|0,1,...     0,1|0,0,0,1,0,0,0,0,0,1,0,1,0,0|...  # Zeile1
    #  |0,1,0,0,0,1,0,0,0,0,0,1,0,0|0,0,...     0,1|0,0,0,1,0,0,0,0,0,1,0,0,0,0|...  # Zeile2
    #  |0,1,0,1,0,1,0,0,0,0,0,1,0,0|0,1,...     0,1|0,1,0,1,0,0,0,0,0,1,0,0,0,1|...  # Zeile3
    #  |0,0,0,0,0,1,0,0,0,0,0,1,0,0|0,0,...     0,0|0,0,0,1,0,0,0,0,0,1,0,0,0,0|...  # Zeile4
    #  |0,0,0,0,0,1,0,0,0,0,0,1,0,1|0,1,...     0,0|0,0,0,1,0,0,0,0,0,1,0,1,0,1|...  # Zeile5
    #  |0,0,0,0,0,0,0,0,0,0,0,0,0,0|0,0,...     0,0|0,0,0,0,0,0,0,0,0,0,0,0,0,0|...  # Zeile6
    #  -----------------------------               -----------------------------

    i=0     # Zaehlvariable zum Verschieben des Ausschnittes im Vektor 'text' um eine Spalte nach rechts
    r=0     # Zaehlvariable fuer die aktuelle Zeile im Datenvektor
    columns_length = int(len(text)/rows)    # Anzahl der Spalten des gesammten Lauftextes
                                            # int(), weil bei Bruchrechnung x,0 rauskommt ...muss aber ohne Kommastelle sein, da dieser Wert Spaeter als Index genutzt wird

    while i <= columns_length-columns:      # Solange rechter Rand des Lauftextes noch nicht erreicht wurde und:
        while r < rows:                     # solange die letzte Zeile nicht ueberschritten wurde
            data[r*columns:columns+r*columns] = text[i+r*columns_length:i+columns_length+r*columns_length] # Schreibe den mit i ausgewaehlten Ausschnitt des Lauftextes auf auf die entsprechende Zeile r in'data'
            r=r+1                                                                                          # erhoehe Zeile um 1

        r=0                                 # Zuruecksetzen der Zaehlvariable fuer die aktuelle Zeile
        Blink_Screen(0.15, 0, data)         # Ausgabe des aktuellen Ausschnittes
        i=i+2                               # Verschiebe den Ausschnitt im Vektor 'text' um eine LED-Spalte (=2 Spalten im Lauftext) nach rechts

def Fall_Animation(r):
    # Funktion zur Animation einer Fallenden LED auf der LED-Matrix bei betaetigen des Enter-Buttons
    # Dazu wird eine 1 (LED AN) innerhalb der aktuellen Spalte einmal durch alle Zeilen geschoben und fuer jeweils 0,05s pro Zeile ausgegeben
    # Dabei ist die aktuelle Position 'pos' bereits an der Zielposition, also an der Position, wo die LED "hinfaellt"
    # Diese Zielposition ist abhaengig davon, wieweit die ausgewaehlte Spalte bereits beim Spielen "aufgefuellt" wurde

    global data # Aufruf der globalen Variable 'data' (da diese innerhalb der Funktion veraendert wird)

    r_start=rows-r-1                    # Berechnung der Startreihe aus der akteullen Zeile
    fall_pos_old = pos-r_start*columns  # Initialwert der zuletzt akteullen Position in der Spalte
    r=1                                 # Variable fuer aktuelle Zeile

    while r*columns < pos:              # Solange die Zielposition beim "Fallen" noch nicht erreicht wurde:
        fall_pos = pos-r_start*columns+r*columns    # erhoehe die Fallposition um eine Zeile
        data[fall_pos]=1                            # Setze data der aktuellen Fallposition auf 1
        data[fall_pos_old]=0                        # Setze data der alten Fallposition (Position, von der man beim "Fallen" kommt)
        Blink_Screen(0.05, 0, data)                 # Ausgabe

        fall_pos_old = fall_pos                     # Setze die alte Fallposition auf die aktuelle
        r=r+1                                       # Erhoehe die Zeile um 1
    data[fall_pos_old]=0                # Zueletzt muss data der letzten Fallposition wieder auf 0 gesetzt werden, danach wird die Animation beendet

### ISR Interrupt-Funktion
# Diese sogenannten Call-Back-Functions (Funktionen, die durch GPIO.add_event_detect aufgerufen werden)
# laufen PARALLEL zum Hauptprogramm
# Es koennen mehrere Callback-Funktionen durch einen GPIO.add_event_detect aufgerufen werden, diese werden jedoch sequenziell
# abgearbeitet (aber parallel zum Hauptprogramm, siehe https://sourceforge.net/p/raspberry-gpio-python/wiki/Inputs/)

def Reset(button_nr):
    # Funktion fuer Reset des Hauptprogramms
    # Wird Enter-Button 2s betaetigt, wird 'reset' auf 1 gesetzt
    # dadurch wird das Hauptprogramm unterbrochen und neu initialisiert
    global reset
    time_start = time.time()       #  Funktionsaufruf, Return the time in seconds since the epoch as a floating point number from the system clock.
    time_reset = 2                 # [t] = seconds, Zeit die gewartet werden soll (Die der Enterbutton betaetigt werden soll)

    # Schleife ueberprueft, ob die aktuelle Systemzeit die Startsystemzeit + den zu wartenden Wert in sec bereits erreicht hat
    # Dabei wird alle 200ms ueberprueft, ob der Enter-Butten bereits wieder losgelassen wurde
    while time.time() < time_start + time_reset:    # Wenn die Wartezeit von 2s noch nicht erreicht wurde:
        time.sleep(0.2)                             # -> schalfe 200ms
        if GPIO.input(BUTTON_ENTER) == 1:           # Ueberpruefe, ob Enter-Butten losgelassen wurde, wenn ja:
            return                                  # Beende Funktion, ohne reset auszuloesen
    reset=1                                         # Falls Wartezeit erreicht wurde und Enter-Button noch immer betaetigt
                                                    # -> Setze 'reset'

### Interrupt Events
GPIO.add_event_detect(BUTTON_ENTER, GPIO.FALLING, callback = Reset, bouncetime = 200)


#------------------------------------------------------------------------#
#                                 Main                                   #
#------------------------------------------------------------------------#

### Initialisierung"

Output_Enable()                     # Funktionsaufruf, aktiviere Ausgaenge der Schieberegisterbausteine
Clear_Shift_Register()              # Funktionsaufruf, loesche aktuellen Inhalt der Shift-Register
Set_Storage_Register()              # Funktionsaufruf, Ausgabe des leeren Shift-Registers
Send_Running_Text(Sample(7))        # Funktionsaufruf, Ausgabe des Startbildschirms ('4 Gewinnt')
while True:
    reset = 0                           # reset zuruecksetzen (nachdem Reset ausgeloest wurde)
    pos = 0                             # position zuruecksetzen (nachdem Reset ausgeloest wurde)
    player_nr = 0                       # player_nr zuruecksetzen (nachdem Reset ausgeloest wurde)
    data = Sample(0)                    # Funktionsaufruf, schreibe Startbildschirm (Sample(0)) auf 'data'

    ### Hauptprogramm
    while reset == 0:					# Solange reset nicht gesetzt wurde (reset wird durch Reset-Funktion, Spielgewinn oder Unentschieden ausgeloest)
        Send_Data(data)                 # Funktionsaufruf, Sende 'data' an LED-Matrix

        if Button(BUTTON_LEFT)== 1:
            # If-Anweisung zum Bewegen eines Bits (bzw. ein eingeschalteten LED) innerhalb der LED-Matrix nach links
            # dabei befindet sich das Bit/die LED in der oberen Zeile der Matrix
            pos_old = pos               # Merke die aktuelle Position in der Matrix
                                        # nach Initialisierung auf 0(-> oben links in der Matrix)

            if pos > 0+player_nr:       # Wenn die aktuelle Position noch nicht den linken Rand der MATRIX erreicht hat:
                pos=pos-2               # Verringere aktuelle Position um 2 Schritte (nach links), (nicht 1, da |g,r|g,r|...)
                while pos >= 0+player_nr:       # Solange aktuelle Position >= 0 (->nicht den linken Rand der Matrix uberschreiten):
                    if Position_Check(1) and pos > 0+player_nr:     # Wenn 'data' an der aktuellen Position 1 und der linke Rand noch nicht erreicht ist:
                        pos=pos-2                                   # -> Verringere aktuellen Position um weitere 2 Schritte
                    elif Position_Check(1) and pos == 0+player_nr:  # Wenn 'data' an der aktuellen Position 1 und der linke Rand erreicht ist:
                        pos=pos_old                                 # -> Setze aktuelle Position zurueck auf Ausgangsposition
                        break                                       # -> Beende Schleife ->nichts passiert
                    else:                                           # Sonst:
                        data[pos] = 1                               # -> Setze 'data' der aktuellen Position auf 1
                        data[pos_old] = 0                           # -> Setze 'data' der alten Position auf 0
                        break                                       # -> Beende Schleife

        if Button(BUTTON_ENTER) == 1:
            # If-Anweisung zum Setzen eines Bits (bzw. einer eingeschalteten LED) innerhalb der LED-Matrix nach unten in
            # das letzte leere Feld der ausgewaehlten Spalte (leeres Feld = 0)

            r=0                             # Zaehlvariable zum durchsuchen der Zeilen einer Spalte nach dem untersten leeren Feld
            pos_old = pos                   # Merke die aktuelle Position in der Matrix
            data[pos] = 0                   # -> Setze 'data' der aktuellen Position auf 0
            pos=pos+(rows-1)*columns    	# Position wird auf die letzte Zeile der aktuellen Spalte geschoben

            while r < rows:     # Solange die obere Zeile nicht ueberschritten wird:
                if  Position_Check(1):      # Wenn 'data' an der aktuellen Position 1 ist:
                    r=r+1                   # -> Erhoehe Zaehlvariable um 1
                    pos=pos-columns         # -> Erhoehe die aktuelle Position um eine Zeile nach oben
                else:                       # Sonst:
		    # Diese If-Anweisung prueft, ob die aktuell erreichte Position der urspruenglichen Position (oberste Zeile) entspricht
                    # Diese Abfage ist wichtig, da sonst die Matrix an der aktuellen Position auf 1 und danach gleich wieder auf 0 gesetzt wird
                    # Dadurch koennte man niemals die obere Zeile beschreiben
                    if pos!=pos_old:        # Wenn die aktuelle Position nicht der urspruenglichen Position entspricht (heisst: aktuelle Position hat noch nicht wieder die obere Zeile erreicht):
                        data[pos_old] = 0   # -> Setze 'data' der alten Position auf 0 (LED in der oberen Zeile ausschalten, ausser diese ist das letzte freie Feld in der Spalte)
                        Fall_Animation(r)   # -> Funktionsaufruf, Fallanimation
                    data[pos] = 1           # -> Setze 'data' der aktuellen Position auf 1
                    break                   # -> Beende Schleife

            # Ueberpruefe, ob 4 in einer Reihe (horizontal, vertikal, diagonal)
            if Win_Check(r)==1:             # Funktionsaufruf, Wenn 4 in einer Reihe:
                #print(win_row)
                Win_Screen()                # -> Funktionsaufruf, Starte Gewinner-Bildschirm
                reset=1                     # -> Setze reset und
                break                       # -> beende Hauptprogramm -> Hauptprogramm wird neu initialisiert

            # Toogle Player and reset position
            player_nr = not player_nr       # Toggle Player Number ( 0...Player 1, 1...Player 2)
            pos = 0+player_nr               # Setze aktuelle Position zurueck auf Startposition (oben links)

            # Pruefe, ob auf der aktuellen Position bereits eine 1 ist (LED an)
            while pos <= pos_max+player_nr: # solange der linke Rand der Matrix nicht ueberschritten wurde:
                if Position_Check(1):       # Wenn 'data' an der aktuellen Position 1 ist:
                    pos=pos+2               # -> Verschiebe Position um eine LED der entsprechenden Spielerfarbe nach rechts
                else:                       # Sonst:
                    data[pos] = 1           # -> Setze 'data' der aktuellen Position auf 1
                    break

            # Pruefe, ob die Matrix bereits komplett ausgefuellt wurde (ohne dass bereits ein Sieg errungen wurde)
            if pos > pos_max+player_nr:	    # Sollte die Position beim 'Ueberpruefen der aktuellen Position auf eine 1' den rechten Rand der Matrix ueberschritten haben
                Draw_Screen()		    	# -> Funktionsaufruf, Starte Unentschieden-Bildschirm
                reset=1                     # -> Setze reset und
                break                       # -> beende Hauptprogramm -> Hauptprogramm wird neu initialisiert



        if Button(BUTTON_RIGHT)==1:
            # If-Anweisung zum Bewegen eines Bits (bzw. ein eingeschalteten LED) innerhalb der LED-Matrix nach rechts
            # dabei befindet sich das Bit/die LED in der oberen Zeile der Matrix
            # -> siehe Anweisung 'if Button(BUTTON_LEFT)== 1:'
            pos_old = pos

            if pos < pos_max + player_nr:
                pos=pos+2
                while pos <= pos_max + player_nr:

                    if Position_Check(1) and pos < pos_max+player_nr:
                        pos=pos+2
                    elif Position_Check(1) and pos == pos_max+player_nr:
                        pos=pos_old
                        break
                    else:
                        data[pos] = 1
                        data[pos_old] = 0
                        break

##GPIO.cleanup()             # Setzt die GPIOs zurueck
##sys.exit()                 # Apparently sys.exit() allows the program to clean up resources and exit
##                           # gracefully, while os._exit() is rather abrupt.
