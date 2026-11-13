PHYSICS_VERSION = "0.1.0"  # 물리 모델 버전 (사람이 관리, specs/001 research R5)

from .geometry import CapsuleTank
from .heat import mli_heat_flux, vacuum_pressure
from .model import BoiloffModel, DesignParams, simulate
from .cost import CostParams, CostResult, analytic_optimal_layers, cost_from_curve, cost_vs_layers, evaluate_cost
