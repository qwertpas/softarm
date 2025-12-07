import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import root_scalar

# --- Constants ---
GAMMA = 1.4
R = 287.05
T0 = 293.15      # 20 C
P_ATM = 101325.0 # Pa
MU = 1.81e-5     # Viscosity (Pa*s)
RHO_STD = 1.204  # kg/m^3

# --- Parameters ---
d_mm = 5.0
D = d_mm / 1000.0
A = np.pi * (D/2)**2
roughness_mm = 0.0015
epsilon = roughness_mm / 1000.0
P_supply_psi = 10.153
P0_pa = (P_supply_psi * 6894.76) + P_ATM


# --- 1. Fanno Flow Solver (The "Ground Truth") ---
def get_fanno_parameter(M):
    if M <= 0 or M >= 1: return np.inf
    term1 = (1 - M**2) / (GAMMA * M**2)
    term2 = (GAMMA + 1) / (2 * GAMMA) * np.log(((GAMMA + 1) * M**2) / (2 + (GAMMA - 1) * M**2))
    return term1 + term2

def friction_factor_haaland(Re, D, eps):
    if Re < 2300: return 64.0 / Re if Re > 0 else 0
    term = (eps / (3.7 * D))**1.11 + (6.9 / Re)
    return (-1.8 * np.log10(term))**-2

def calculate_mass_flow(M, P_stag, T_stag, Area):
    term = (1 + (GAMMA-1)/2 * M**2)**(-(GAMMA+1)/(2*(GAMMA-1)))
    return Area * P_stag / np.sqrt(R * T_stag) * np.sqrt(GAMMA) * M * term

def solve_fanno(L_m):
    # Iterative solver for Fanno flow
    def find_M1(m1_guess):
        m_dot = calculate_mass_flow(m1_guess, P0_pa, T0, A)
        Re = 4 * m_dot / (np.pi * D * MU)
        f = friction_factor_haaland(Re, D, epsilon)
        
        target_fanno_consumption = 4 * f * L_m / D
        fanno_M1 = get_fanno_parameter(m1_guess)
        
        # Check choking condition first
        # Max length possible for this M1 is when M2=1, i.e. Fanno(M2)=0
        # So max consumption = Fanno(M1). 
        # If target > Fanno(M1), flow is CHOKED.
        
        # We need to find the specific M1 that matches the boundary condition.
        # IF Unchoked: Boundary is P_exit = P_atm
        # IF Choked: Boundary is M_exit = 1 (and P_exit > P_atm)
        
        # To make this robust, let's just solve for "What is the M1 if exit is P_atm?"
        # If that M1 implies M_exit > 1 (impossible), then it's Choked.
        
        return 0 # Placeholder structure, better logic below
    
    # Robust Logic:
    # 1. Find the Limiting M1 (Choked case)
    def choked_resid(m1):
        m_dot = calculate_mass_flow(m1, P0_pa, T0, A)
        Re = 4 * m_dot / (np.pi * D * MU)
        f = friction_factor_haaland(Re, D, epsilon)
        return get_fanno_parameter(m1) - (4 * f * L_m / D)

    try:
        sol_limit = root_scalar(choked_resid, bracket=[0.0001, 0.999], method='brentq')
        M1_choked = sol_limit.root
    except:
        return np.nan # Solver failed

    # Calculate Exit Pressure for this Choked Case
    P1 = P0_pa * (1 + (GAMMA-1)/2 * M1_choked**2)**(-GAMMA/(GAMMA-1))
    # P*/P1 = M1 * sqrt(...)
    P_star = P1 * M1_choked * np.sqrt((2 + (GAMMA-1)*M1_choked**2)/(GAMMA+1))
    
    if P_star >= P_ATM:
        # It is choked
        m_dot = calculate_mass_flow(M1_choked, P0_pa, T0, A)
        return m_dot / RHO_STD
    else:
        # It is Subsonic
        # Solve for M1 such that P_exit = P_ATM
        def subsonic_resid(m1):
            m_dot = calculate_mass_flow(m1, P0_pa, T0, A)
            Re = 4 * m_dot / (np.pi * D * MU)
            f = friction_factor_haaland(Re, D, epsilon)
            
            fanno_1 = get_fanno_parameter(m1)
            fanno_2_needed = fanno_1 - (4 * f * L_m / D)
            
            if fanno_2_needed < 0: return -1e9 # Impossible
            
            # Find M2 from Fanno(M2)
            # Fanno decreases with M. 
            def find_m2(m): return get_fanno_parameter(m) - fanno_2_needed
            try:
                # M2 > M1
                m2 = root_scalar(find_m2, bracket=[m1, 0.9999], method='brentq').root
            except:
                return -1e9
                
            # Check Pressure
            P1 = P0_pa * (1 + (GAMMA-1)/2 * m1**2)**(-GAMMA/(GAMMA-1))
            P2 = P1 * (m1/m2) * np.sqrt((2+(GAMMA-1)*m1**2)/(2+(GAMMA-1)*m2**2))
            return P2 - P_ATM

        try:
            sol_sub = root_scalar(subsonic_resid, bracket=[0.0001, M1_choked], method='brentq')
            m_dot = calculate_mass_flow(sol_sub.root, P0_pa, T0, A)
            return m_dot / RHO_STD
        except:
            return np.nan

# --- 2. Isothermal Compressible Flow Solver ---
def solve_isothermal(L_m):
    # m_dot = A * sqrt( (P1^2 - P2^2) / (RT * (fL/D + 2ln(P1/P2))) )
    # Requires f, which requires Re, which requires m_dot -> Iterative
    
    P_in = P0_pa # Approximation: neglecting acceleration P0->P1 for this simple model
    P_out = P_ATM
    
    m_dot_guess = 0.005 # Init
    for _ in range(10):
        Re = 4 * m_dot_guess / (np.pi * D * MU)
        f = friction_factor_haaland(Re, D, epsilon)
        print(f"{_}: f={f}, m_dot_guess{m_dot_guess}")
        
        term_denom = R * T0 * (f * L_m / D + 2 * np.log(P_in/P_out))
        if term_denom <= 0: break
        m_dot_new = A * np.sqrt( (P_in**2 - P_out**2) / term_denom )
        
        if abs(m_dot_new - m_dot_guess) < 1e-6:
            m_dot_guess = m_dot_new
            break
        m_dot_guess = m_dot_new
        
    return m_dot_guess / RHO_STD

def solve_isothermal_simple(L_m):
    f=0.02
    P_in = P0_pa
    P_out = P_ATM
    m_dot = A * np.sqrt( (P_in**2 - P_out**2) / (R * T0 * (f * L_m / D + 2 * np.log(P_in/P_out))) )
    return m_dot/RHO_STD


# --- RUN COMPARISON ---
lengths = np.linspace(0.2, 3.0, 20)
results_fanno = []
results_iso = []
results_iso_simple = []

for l in lengths:
    results_fanno.append(solve_fanno(l))
    results_iso.append(solve_isothermal(l))
    results_iso_simple.append(solve_isothermal_simple(l))

# Plot
plt.figure(figsize=(10, 6))
plt.plot(lengths, results_fanno, 'b-', linewidth=2, label='Fanno Flow (Physics Baseline)')
plt.plot(lengths, results_iso, 'g--', linewidth=2, label='Isothermal Equation')
plt.plot(lengths, results_iso_simple, 'r--', linewidth=2, label='Isothermal Simple Equation')

# Add user's specific data points for context
plt.scatter([1.0], [solve_fanno(1.0)], color='blue', zorder=5)
plt.annotate(f"Fanno (1m): {solve_fanno(1.0):.4f}", (1.0, solve_fanno(1.0)), xytext=(10, 10), textcoords='offset points')

plt.title('Air Flow Rate vs. Tube Length (5mm ID @ 20 psi)')
plt.xlabel('Tube Length (m)')
plt.ylabel('Flow Rate (Standard m^3/s)')
plt.grid(True, which='both', linestyle='--', alpha=0.7)
plt.legend()
plt.tight_layout()
plt.ylim(0, None)
# plt.savefig('flow_comparison.png')
plt.show()