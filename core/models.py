# core/models.py

from django.db import models

class FinancialAssumptions(models.Model):
    # Coûts d'investissement
    cost_per_kwc_solar = models.FloatField(default=1200) # Coût en € par kWc installé (panneaux, structure, onduleur...)
    cost_per_kw_pump = models.FloatField(default=500) # Coût en € par kW de la pompe
    installation_fees_percent = models.FloatField(default=15) # % du coût matériel pour l'installation

    # Coûts opérationnels
    maintenance_percent_per_year = models.FloatField(default=1.5) # % du coût d'invest. pour la maintenance annuelle

    # Paramètres de comparaison
    cost_per_kwh_grid = models.FloatField(default=0.14) # Coût du kWh du réseau (SBEE)
    cost_per_kwh_diesel = models.FloatField(default=0.45) # Coût du kWh d'un générateur diesel (carburant + maintenance)

    # Paramètres financiers
    system_lifespan_years = models.IntegerField(default=25) # Durée de vie du système
    discount_rate_percent = models.FloatField(default=5) # Taux d'actualisation pour le LCOE

    def __str__(self):
        return "Hypothèses Financières Actives"

class SolarPanel(models.Model):
    brand = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    power_watt = models.IntegerField()
    efficiency = models.FloatField()
    cost = models.FloatField() # Coût par panneau

    def __str__(self):
        return f"{self.brand} {self.model_name} - {self.power_watt}W"

class WaterPump(models.Model):
    brand = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    power_kw = models.FloatField()
    max_flow_rate_m3_h = models.FloatField()
    max_hmt = models.FloatField()
    cost = models.FloatField()

    def __str__(self):
        return f"{self.brand} {self.model_name} - {self.power_kw}kW"
        

class SimulationResult(models.Model):
    # Un nom pour la simulation, pour que l'utilisateur s'y retrouve
    name = models.CharField(max_length=200, default='Simulation sans nom')
    created_at = models.DateTimeField(auto_now_add=True)

    # Inputs de la simulation
    latitude = models.FloatField()
    longitude = models.FloatField()
    volume_eau = models.FloatField()
    hmt = models.FloatField()

    # Outputs (on stocke le JSON complet des résultats pour plus de flexibilité)
    # C'est une méthode très efficace pour sauvegarder des données structurées.
    results_json = models.JSONField()

    def __str__(self):
        return f"{self.name} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        ordering = ['-created_at'] # Les plus récents en premier
        

class Battery(models.Model):
    brand = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    voltage = models.IntegerField() # en Volts (ex: 12, 24, 48)
    capacity_ah = models.IntegerField() # Capacité en Ampères-heure (ex: 100, 200)
    dod_percent = models.FloatField(default=50) # Profondeur de Décharge max (%)
    efficiency = models.FloatField(default=85) # Rendement aller-retour (%)
    cost = models.FloatField() # Coût par batterie

    def __str__(self):
        return f"{self.brand} {self.model_name} - {self.voltage}V {self.capacity_ah}Ah"

    @property
    def capacity_kwh(self):
        # Capacité totale en kWh
        return (self.voltage * self.capacity_ah) / 1000

    @property
    def usable_capacity_kwh(self):
        # Capacité réellement utilisable en kWh, en tenant compte de la DoD
        return self.capacity_kwh * (self.dod_percent / 100)
