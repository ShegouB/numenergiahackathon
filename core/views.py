# core/views.py

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from weasyprint import HTML
import json
import requests
import math
from datetime import datetime
from .models import FinancialAssumptions, SolarPanel, WaterPump, SimulationResult, Battery, User
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.views import generic
from django.db.models import F, FloatField
from django.db.models.functions import Cast 


class SignUpView(generic.CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login') 
    template_name = 'registration/signup.html'

@login_required 
def index_view(request):
    return render(request, 'index.html')


RHO, G, ETA_POMPE, PERTES_SYSTEME = 1000, 9.81, 0.4, 0.75
PVGIS_API_BASE_URL = "https://re.jrc.ec.europa.eu/api/"

def get_solar_irradiation(lat, lon):
    api_url = f"{PVGIS_API_BASE_URL}PVcalc?lat={lat}&lon={lon}&peakpower=1&loss=14&outputformat=json"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data['outputs']['totals']['fixed']['E_d'], True
    except requests.exceptions.RequestException as e:
        print(f"AVERTISSEMENT API PVGIS (journalier): {e}. Utilisation de la valeur par défaut.")
        return 5.0, False

@login_required
@csrf_exempt
def calculate_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
           
            print("Données reçues pour le calcul:", data)

            
            autonomy_days = float(data.get('autonomy_days', 0))
            lat, lon = data['lat'], data['lon']
            volume_eau_m3, hmt_m = float(data['volume']), float(data['hmt'])
            optimization_target = data.get('optimization_target', 'performance')

            
            energie_hydraulique_J = RHO * G * volume_eau_m3 * hmt_m
            energie_electrique_J = energie_hydraulique_J / ETA_POMPE
            energie_electrique_kwh = energie_electrique_J / (3.6 * 1e6)
            irradiation_kwh_m2_jour, pvgis_online = get_solar_irradiation(lat, lon)

            
            battery_data, number_of_batteries, best_battery = None, 0, None
            if autonomy_days > 0:
                best_battery = Battery.objects.annotate(
                    computed_capacity=Cast(F('voltage') * F('capacity_ah'), output_field=FloatField())
                ).order_by('-computed_capacity').first()
                if not best_battery: raise Exception("Aucune batterie dans la BDD.")
                total_energy_to_store_kwh = energie_electrique_kwh * autonomy_days
                single_battery_usable_kwh = best_battery.usable_capacity_kwh
                if single_battery_usable_kwh > 0: number_of_batteries = math.ceil(total_energy_to_store_kwh / single_battery_usable_kwh)
                battery_data = { 'model': f"{best_battery.brand} {best_battery.model_name}", 'quantity': number_of_batteries, 'total_capacity_kwh': round(number_of_batteries * best_battery.capacity_kwh, 2), 'usable_capacity_kwh': round(number_of_batteries * single_battery_usable_kwh, 2) }

            energy_for_battery_charge = energie_electrique_kwh / (best_battery.efficiency / 100) if best_battery and autonomy_days > 0 else 0
            total_daily_generation_kwh = energie_electrique_kwh + energy_for_battery_charge
            if optimization_target == 'performance': total_daily_generation_kwh *= 1.15
            puissance_crete_kwc = total_daily_generation_kwh / (irradiation_kwh_m2_jour * PERTES_SYSTEME) if irradiation_kwh_m2_jour > 0 else 0
            puissance_pompe_kw = puissance_crete_kwc * 0.8
            
           
            component_data, best_panel, best_pump, number_of_panels = None, None, None, 0
            required_power_watt = puissance_crete_kwc * 1000
            if optimization_target == 'budget':
                best_panel = SolarPanel.objects.filter(power_watt__gt=250).order_by('cost').first() 
                best_pump = WaterPump.objects.filter(power_kw__gte=puissance_pompe_kw).order_by('cost').first()
            else:
                best_panel = SolarPanel.objects.order_by('-efficiency', '-power_watt').first()
                best_pump = WaterPump.objects.filter(power_kw__gte=puissance_pompe_kw).order_by('power_kw').first()
            if not best_pump: best_pump = WaterPump.objects.filter(power_kw__gte=puissance_pompe_kw).order_by('cost').first()
            if not best_panel: raise Exception("Aucun panneau solaire ne correspond aux critères.")
            if not best_pump: raise Exception("Aucune pompe ne correspond aux critères.")
            number_of_panels = math.ceil(required_power_watt / best_panel.power_watt) if best_panel.power_watt > 0 else 0
            component_data = { 'panel_model': f"{best_panel.brand} {best_panel.model_name}", 'panel_power_watt': best_panel.power_watt, 'panel_quantity': number_of_panels, 'pump_model': f"{best_pump.brand} {best_pump.model_name}", 'pump_power_kw': best_pump.power_kw }

           
            financial_data = None
            assumptions = FinancialAssumptions.objects.first()
            if not assumptions: raise Exception("Hypothèses financières non configurées.")
            battery_cost = number_of_batteries * best_battery.cost if best_battery else 0
            material_cost = (number_of_panels * best_panel.cost) + best_pump.cost + battery_cost
            installation_cost = material_cost * (assumptions.installation_fees_percent / 100)
            total_investment = material_cost + installation_cost
            lifespan = int(data.get('lifespan', assumptions.system_lifespan_years))
            maintenance_cost_annual = total_investment * (assumptions.maintenance_percent_per_year / 100)
            lifetime_costs = total_investment + (maintenance_cost_annual * lifespan)
            lifetime_energy_production_kwh = energie_electrique_kwh * 365 * lifespan
            lcoe = lifetime_costs / lifetime_energy_production_kwh if lifetime_energy_production_kwh > 0 else 0
            financial_data = { 'total_investment': round(total_investment, 2), 'lcoe': round(lcoe, 3), 'cost_vs_diesel_per_year': round((assumptions.cost_per_kwh_diesel - lcoe) * (energie_electrique_kwh * 365), 2) }

          
            response_data = {
                'technical': { 'puissance_requise_kwc': round(puissance_crete_kwc, 2), 'puissance_pompe_kw': round(puissance_pompe_kw, 2), 'irradiation_locale_kwh_m2': round(irradiation_kwh_m2_jour, 2), 'energie_journaliere_kwh': round(energie_electrique_kwh, 2), 'pvgis_online': pvgis_online },
                'financials': financial_data, 'components': component_data, 'battery': battery_data
            }
            
            full_simulation_data = {
                'inputs': { 'name': data.get('project_name', f"Projet à {lat:.2f}, {lon:.2f}"), 'latitude': lat, 'longitude': lon, 'volume_eau': volume_eau_m3, 'hmt': hmt_m, 'autonomy_days': autonomy_days, 'optimization_target': optimization_target },
                'results': response_data
            }
            
            
            sim_instance = SimulationResult.objects.create(
                user=request.user, 
                name=full_simulation_data['inputs']['name'],
                latitude=lat, longitude=lon, volume_eau=volume_eau_m3, hmt=hmt_m,
                simulation_data_json=full_simulation_data
            )
            full_simulation_data['created_at'] = sim_instance.created_at.strftime('%d/%m/%Y %H:%M')
            
            return JsonResponse(full_simulation_data)
        
        except Exception as e:
            print(f"ERREUR SERVEUR DANS CALCULATE_API: {e}")
            return JsonResponse({'error': f'Une erreur interne est survenue sur le serveur: {e}'}, status=500)
    
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@login_required
@csrf_exempt
def hourly_production_api(request):
    if request.method == 'POST':
        FALLBACK_CURVE = [ 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.05, 0.20, 0.50, 0.80, 0.95, 1.00, 1.00, 0.95, 0.80, 0.50, 0.20, 0.05, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00 ]
        
        try:
            data = json.loads(request.body)
            lat, lon, peak_power_kwc = data.get('lat'), data.get('lon'), data.get('kwc')

            if not all([lat, lon, peak_power_kwc]):
                return JsonResponse({'error': 'Données manquantes'}, status=400)

            api_url = f"{PVGIS_API_BASE_URL}seriescalc?lat={lat}&lon={lon}&pvcalculation=1&loss=14&outputformat=json"
            
            response = requests.get(api_url, timeout=5)
            response.raise_for_status()
            pvgis_data = response.json()
            
            if 'hourly' not in pvgis_data.get('outputs', {}): raise ValueError("La réponse de l'API PVGIS ne contient pas de données horaires.")

            hourly_data = pvgis_data['outputs']['hourly']
            avg_hourly_production_w_per_kwc = [0] * 24
            num_days = len(hourly_data) / 24
            if num_days < 1: raise ValueError("Données horaires insuffisantes.")

            for record in hourly_data:
                hour_of_day = int(record['time'][9:11])
                avg_hourly_production_w_per_kwc[hour_of_day] += record['P']
            
            avg_hourly_production_kw = [
                round(((s / num_days) / 1000) * peak_power_kwc, 2) 
                for s in avg_hourly_production_w_per_kwc
            ]
            return JsonResponse(avg_hourly_production_kw, safe=False)

        except (requests.exceptions.RequestException, KeyError, ValueError) as e:
            print(f"AVERTISSEMENT API PVGIS (horaire): {e}. Utilisation de la courbe de secours.")
            fallback_production = [round(val * peak_power_kwc, 2) for val in FALLBACK_CURVE]
            return JsonResponse(fallback_production, safe=False)
            
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@login_required 
@csrf_exempt
def history_api(request):
    if request.method == 'GET':
        simulations = SimulationResult.objects.filter(user=request.user)[:20]
        data = []
        for sim in simulations:
            sim_data = sim.simulation_data_json
            sim_data['created_at'] = sim.created_at.strftime('%d/%m/%Y %H:%M')
            data.append({
                'id': sim.id,
                'simulation_data': sim_data
            })
        return JsonResponse(data, safe=False)
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

@login_required
@csrf_exempt
def generate_pdf_report(request):
    if request.method == 'POST':
        simulation_data = json.loads(request.body)
        if 'inputs' not in simulation_data or 'results' not in simulation_data:
            return HttpResponse("Format de données de simulation invalide.", status=400)

        context_data = {
            'simulation': simulation_data,
            'simulation_date': datetime.now().strftime('%d/%m/%Y')
        }
        
        html_string = render_to_string('report_template.html', context_data)
        
        try:
            pdf_file = HTML(string=html_string).write_pdf()
            response = HttpResponse(pdf_file, content_type='application/pdf')
            file_name = f"rapport_numenergia_{simulation_data['inputs'].get('name', 'projet')}.pdf".replace(' ', '_')
            response['Content-Disposition'] = f'attachment; filename="{file_name}"'
            return response
        except Exception as e:
            print(f"Erreur de génération PDF avec WeasyPrint: {e}")
            return HttpResponse("Erreur lors de la génération du rapport.", status=500)
            
    return HttpResponse("Méthode non autorisée", status=405)
    