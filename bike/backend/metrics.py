"""Time-weighted session statistics, independent of the decimated plot trace."""
import math
from copy import deepcopy


def normalize_summary(summary, mode):
    """Fail closed for historical Daum setpoint-like data, without DB edits."""
    value = deepcopy(summary) if isinstance(summary, dict) else {}
    quality = value.get('measurement_quality') if isinstance(value.get('measurement_quality'),dict) else {}
    verified = value.get('power_measurement_verified') is True and quality.get('power_watts') == 'verified_measured'
    if mode != 'daum' or verified:
        return value
    averages = dict(value['averages']) if isinstance(value.get('averages'),dict) else {}
    coverage = dict(value['coverage_seconds']) if isinstance(value.get('coverage_seconds'),dict) else {}
    if averages.get('power_watts') is not None:
        value.setdefault('reported_unverified_power_watts', averages['power_watts'])
    if value.get('mechanical_energy_kj') is not None:
        value.setdefault('reported_unverified_mechanical_energy_kj', value['mechanical_energy_kj'])
    averages['power_watts'] = None
    coverage['power_watts'] = 0
    value.update(averages=averages, coverage_seconds=coverage, mechanical_energy_kj=None,
                 power_measurement_verified=False,
                 measurement_quality={**quality, 'power_watts':'device_reported_unverified'},
                 power_measurement_note='Daum-X70-Wattdaten sind nicht als unabhängige Ist-Leistungsmessung nachgewiesen. Frühere numerische Werte bleiben nur als unverifizierte Gerätemeldung erhalten.')
    sources = dict(value['sources']) if isinstance(value.get('sources'),dict) else {}
    sources['power_watts'] = 'daum_reported_unverified'
    value['sources'] = sources
    return value


class SessionMetrics:
    fields = ('power_watts', 'heart_rate_bpm', 'cadence_rpm')

    def __init__(self):
        self.integrals = dict.fromkeys(self.fields, 0.0)
        self.coverage = dict.fromkeys(self.fields, 0.0)

    def add(self, seconds, power=None, heart_rate=None, cadence=None):
        if not math.isfinite(seconds) or seconds <= 0:
            return
        for key, value in zip(self.fields, (power, heart_rate, cadence)):
            if value is not None and math.isfinite(value) and value >= 0:
                # Missing HR is None; zero is not a physiological HR measurement.
                if key == 'heart_rate_bpm' and value == 0:
                    continue
                self.integrals[key] += value * seconds
                self.coverage[key] += seconds

    def summary(self, duration, simulated=False, weight_kg=None, device_source='daum', measurement_quality=None):
        source = 'demo' if simulated else device_source
        quality = dict(power_watts='simulated' if simulated else 'unverified',
                       heart_rate_bpm='sensor_reported', cadence_rpm='simulated' if simulated else 'device_reported')
        quality.update(measurement_quality or {})
        return dict(
            duration_seconds=round(duration, 3),
            averages={key: round(self.integrals[key] / self.coverage[key], 2)
                      if self.coverage[key] else None for key in self.fields},
            coverage_seconds={key: round(self.coverage[key], 3) for key in self.fields},
            mechanical_energy_kj=round(self.integrals['power_watts'] / 1000, 3)
                if self.coverage['power_watts'] else None,
            calories_kcal=None, simulated=simulated, weight_kg=weight_kg,
            measurement_quality=quality,
            power_measurement_verified=quality['power_watts']=='verified_measured',
            sources=dict(power_watts=source, heart_rate_bpm='ble', cadence_rpm=source),
            notes='Zeitgewichtete Mittelwerte nur über gültige Messintervalle. Mechanische kJ sind keine Stoffwechselkalorien.')
