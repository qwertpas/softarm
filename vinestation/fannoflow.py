"""
Fanno Flow Calculator using pygasflow

Computes volumetric flow rate through a tube with friction (Fanno flow)
given tube geometry and pressure conditions.

Usage:
    result = compute_flow(diameter_mm=5.0, length_m=1.0, P_inlet_psi=10, P_outlet_pa=101325)
"""

import numpy as np
from scipy.optimize import root_scalar
import pygasflow.fanno as fanno
import pygasflow.isentropic as isentropic

# --- Constants ---
GAMMA = 1.4          # Specific heat ratio for air
R = 287.05           # Gas constant for air (J/kg·K)
MU = 1.81e-5         # Dynamic viscosity of air (Pa·s)
RHO_STD = 1.204      # Standard air density (kg/m³)
P_ATM = 101325.0     # Atmospheric pressure (Pa)
T0_K=293.15


def friction_factor_haaland(Re, D, epsilon):
    """
    Compute Darcy friction factor using Haaland equation.
    
    Parameters
    ----------
    Re : float
        Reynolds number
    D : float
        Pipe diameter (m)
    epsilon : float
        Surface roughness (m)
    
    Returns
    -------
    f : float
        Darcy friction factor
    """
    if Re < 2300:
        return 64.0 / Re if Re > 0 else 0.0
    term = (epsilon / (3.7 * D))**1.11 + (6.9 / Re)
    return (-1.8 * np.log10(term))**-2


def mass_flow_from_mach(M, P0, T0, A, gamma=GAMMA):
    """
    Compute mass flow rate from Mach number and stagnation conditions.
    
    Uses the isentropic mass flow equation:
    m_dot = A * P0 / sqrt(R*T0) * sqrt(gamma) * M * (1 + (gamma-1)/2 * M^2)^(-(gamma+1)/(2*(gamma-1)))
    
    Parameters
    ----------
    M : float
        Mach number
    P0 : float
        Stagnation pressure (Pa)
    T0 : float
        Stagnation temperature (K)
    A : float
        Cross-sectional area (m²)
    gamma : float
        Specific heat ratio
    
    Returns
    -------
    m_dot : float
        Mass flow rate (kg/s)
    """
    term = (1 + (gamma - 1) / 2 * M**2)**(-(gamma + 1) / (2 * (gamma - 1)))
    return A * P0 / np.sqrt(R * T0) * np.sqrt(gamma) * M * term


def compute_flow(diameter_mm, length_m, P_inlet_psi, P_outlet_pa=P_ATM, 
                 T0_K=293.15, roughness_mm=0.0015, gamma=GAMMA):
    """
    Compute volumetric flow rate through a tube using Fanno flow analysis.
    
    Parameters
    ----------
    diameter_mm : float
        Tube inner diameter (mm)
    length_m : float
        Tube length (m)
    P_inlet_psi : float
        Inlet gauge pressure (psi)
    P_outlet_pa : float, optional
        Outlet pressure (Pa), default atmospheric
    T0_K : float, optional
        Stagnation temperature (K), default 293.15 (20°C)
    roughness_mm : float, optional
        Surface roughness (mm), default 0.0015 (smooth tubing)
    gamma : float, optional
        Specific heat ratio, default 1.4 (air)
    
    Returns
    -------
    dict with keys:
        'Q_std' : Volumetric flow rate at standard conditions (m³/s)
        'Q_slpm' : Volumetric flow rate (standard liters per minute)
        'm_dot' : Mass flow rate (kg/s)
        'M_inlet' : Inlet Mach number
        'M_outlet' : Outlet Mach number  
        'choked' : Whether flow is choked
        'P_exit' : Exit pressure (Pa)
    """
    # Convert units
    D = diameter_mm / 1000.0  # m
    A = np.pi * (D / 2)**2    # m²
    epsilon = roughness_mm / 1000.0  # m
    P0 = (P_inlet_psi * 6894.76) + P_ATM  # Pa (absolute)
    
    # --- Step 1: Find the choked flow condition ---
    # Solve for M1 where: 4fL*/D (at M1) = 4fL/D (consumed by pipe)
    
    def choked_residual(M1):
        """Residual for finding inlet Mach that makes flow exactly choked."""
        m_dot = mass_flow_from_mach(M1, P0, T0_K, A, gamma)
        Re = 4 * m_dot / (np.pi * D * MU)
        f = friction_factor_haaland(Re, D, epsilon)
        
        # Use pygasflow for Fanno parameter
        fp_available = fanno.critical_friction_parameter(M1, gamma)
        fp_consumed = f * length_m / D
        
        return fp_available - fp_consumed
    
    try:
        sol = root_scalar(choked_residual, bracket=[1e-4, 0.9999], method='brentq')
        M1_choked = sol.root
    except ValueError:
        return {'error': 'Could not find choked solution', 'Q_std': np.nan}
    
    # --- Step 2: Check if actually choked by comparing exit pressure ---
    # Get pressure at sonic conditions (M=1)
    # P1/P0 from isentropic, P*/P1 from Fanno
    P1_over_P0 = isentropic.pressure_ratio(M1_choked, gamma)
    P1 = P0 * P1_over_P0
    
    # P/P* from Fanno (this is P1/P*)
    P1_over_Pstar = fanno.critical_pressure_ratio(M1_choked, gamma)
    P_star = P1 / P1_over_Pstar  # Exit pressure if choked
    
    if P_star >= P_outlet_pa:
        # Flow IS choked (M_exit = 1)
        m_dot = mass_flow_from_mach(M1_choked, P0, T0_K, A, gamma)
        Q_std = m_dot / RHO_STD
        
        return {
            'Q_std': Q_std,
            'Q_m3ps': Q_std,  #  m³/s 
            'm_dot': m_dot,
            'M_inlet': M1_choked,
            'M_outlet': 1.0,
            'choked': True,
            'P_exit': P_star
        }
    
    # --- Step 3: Subsonic (unchoked) case ---
    # Find M1 such that exit pressure equals P_outlet
    
    def subsonic_residual(M1):
        """Residual for matching exit pressure to atmospheric."""
        m_dot = mass_flow_from_mach(M1, P0, T0_K, A, gamma)
        Re = 4 * m_dot / (np.pi * D * MU)
        f = friction_factor_haaland(Re, D, epsilon)
        
        # Fanno parameter consumed
        fp_consumed = f * length_m / D
        
        # Fanno parameter available at M1
        fp_at_M1 = fanno.critical_friction_parameter(M1, gamma)
        
        # Remaining Fanno parameter at exit
        fp_at_M2 = fp_at_M1 - fp_consumed
        
        if fp_at_M2 < 0:
            return -1e9  # Invalid
        
        # Find M2 from remaining friction parameter (subsonic branch)
        try:
            M2 = fanno.m_from_critical_friction(fp_at_M2, 'sub', gamma)
        except:
            return -1e9
        
        # Compute exit pressure using Fanno pressure ratios
        # P1/P* and P2/P* -> P2 = P1 * (P2/P*) / (P1/P*)
        P1_over_Pstar = fanno.critical_pressure_ratio(M1, gamma)
        P2_over_Pstar = fanno.critical_pressure_ratio(M2, gamma)
        
        P1 = P0 * isentropic.pressure_ratio(M1, gamma)
        P2 = P1 * P2_over_Pstar / P1_over_Pstar
        
        return P2 - P_outlet_pa
    
    try:
        sol = root_scalar(subsonic_residual, bracket=[1e-4, M1_choked], method='brentq')
        M1 = sol.root
        
        # Recalculate final values
        m_dot = mass_flow_from_mach(M1, P0, T0_K, A, gamma)
        Re = 4 * m_dot / (np.pi * D * MU)
        f = friction_factor_haaland(Re, D, epsilon)
        # print(f)
        
        fp_consumed = f * length_m / D
        fp_at_M1 = fanno.critical_friction_parameter(M1, gamma)
        fp_at_M2 = fp_at_M1 - fp_consumed
        M2 = fanno.m_from_critical_friction(fp_at_M2, 'sub', gamma)
        
        Q_std = m_dot / RHO_STD
        
        return {
            'Q_std': Q_std,
            'Q_slpm': Q_std * 60000,
            'm_dot': m_dot,
            'M_inlet': M1,
            'M_outlet': float(M2),
            'choked': False,
            'P_exit': P_outlet_pa
        }
        
    except ValueError:
        return {'error': 'Could not find subsonic solution', 'Q_std': np.nan}


def compute_isothermal_flow(diameter_mm, length_m, P_inlet_pa, P_outlet_pa, 
                            T0_K=293.15, f=0.021):
    """
    Compute volumetric flow rate using isothermal flow model.
    
    Parameters
    ----------
    diameter_mm : float
        Tube inner diameter (mm)
    length_m : float
        Tube length (m)
    P_inlet_pa : float
        Inlet pressure (Pa, absolute)
    P_outlet_pa : float
        Outlet pressure (Pa, absolute)
    T0_K : float, optional
        Temperature (K), default 293.15 (20°C)
    f : float, optional
        Friction factor, default 0.021
    
    Returns
    -------
    Q_std : float
        Volumetric flow rate at standard conditions (m³/s)
    """
    D = diameter_mm / 1000.0  # m
    A = np.pi * (D / 2)**2    # m²
    
    # Isothermal flow: m_dot = A * sqrt((P_in^2 - P_out^2) / (R*T*(f*L/D + 2*ln(P_in/P_out))))
    if P_outlet_pa >= P_inlet_pa:
        return 0.0
    
    m_dot = A * np.sqrt((P_inlet_pa**2 - P_outlet_pa**2) / 
                        (R * T0_K * (f * length_m / D + 2 * np.log(P_inlet_pa / P_outlet_pa))))
    Q_std = m_dot / RHO_STD
    return Q_std


if __name__ == "__main__":
    import matplotlib.pyplot as plt

    flows = []
    
    lengths = np.linspace(0.2, 10.0, 50)
    psi_values = np.arange(5, 51, 10)
    flows_by_psi = []

    flows_by_psi = []
    choked_flags_by_psi = []

    for psi in psi_values:
        flows = []
        choked_flags = []
        for L in lengths:
            res = compute_flow(diameter_mm=5.0, length_m=L, P_inlet_psi=psi)
            flows.append(res['Q_std'] if 'Q_std' in res else np.nan)
            choked_flags.append(res.get('choked', False))
        flows_by_psi.append(flows)
        choked_flags_by_psi.append(choked_flags)

    # Plot results
    plt.figure(figsize=(10, 6))

    # Define a colormap; use as many colors as there are psi_values
    import matplotlib.pyplot as plt
    colors = plt.cm.rainbow(np.linspace(0, 1, len(psi_values)))

    for i, psi in enumerate(psi_values):
        color = colors[i]

        # Fanno
        plt.plot(lengths, flows_by_psi[i], '-', color=color, label=f'Fanno {psi} psi')

        # Isothermal flow calculation
        f = 0.021
        P_in = psi*6894.76 + P_ATM
        P_out = P_ATM
        T0 = 293.15
        D = 0.005
        A = np.pi * (D / 2)**2    # m²
        m_dot = A * np.sqrt( (P_in**2 - P_out**2) / (R * T0 * (f * lengths / D + 2*np.log(P_in/P_out))) )
        q_isothermal = m_dot/RHO_STD
        plt.plot(lengths, q_isothermal, '--', color=color, label=f'isothermal {psi} psi')

        
        # Engineering equation: ΔP = f * (L/D) * (ρ * v²/2)
        # Solving for v: v = sqrt( (2 * ΔP * D) / (ρ * f * L) )
        # Then Q = v * A
        delta_P = P_in - P_out  # Pressure drop
        P_avg = (P_in + P_out) / 2  # Average pressure for density calculation
        rho_avg = P_avg / (R * T0)  # Average density using ideal gas law
        
        # Calculate velocity for each length
        # Handle division by zero for L=0 case
        v_engineering = np.sqrt((2 * delta_P * D) / (rho_avg * f * np.maximum(lengths, 1e-6)))
        q_engineering = v_engineering * A
        plt.plot(lengths, q_engineering, ':', color=color, label=f'engineering {psi} psi')

        
    plt.xlabel('Tube Length (m)', fontsize=12)
    plt.ylabel('Flow Rate (m$^3$/s)', fontsize=12)
    plt.title('Fanno Flow: 5mm ID Tube @ Various Gauge Pressures', fontsize=14)
    plt.grid(True, alpha=0.3)
    plt.legend(title='Inlet Gauge Pressure')
    plt.tight_layout()
    # plt.show()
    



    # New figure: Q vs P_outlet
    print("\n=== Parametric Study: Flow vs Outlet Pressure ===")
    plt.figure(figsize=(10, 6))
    
    # Fixed parameters
    fixed_length = 1.0  # m
    fixed_diameter_mm = 5.0
    
    # Vary outlet pressure from very low to inlet pressure
    # Use a few different inlet pressures
    inlet_psi_values = np.arange(10,51, 10)
    colors_pressure = plt.cm.rainbow(np.linspace(0, 1, len(inlet_psi_values)))
    
    for i, inlet_psi in enumerate(inlet_psi_values):
        color = colors_pressure[i]
        P_inlet_pa = inlet_psi * 6894.76 + P_ATM
        
        # Vary outlet pressure from 0.1*P_inlet to P_inlet (but not above P_inlet)
        P_outlet_range = np.linspace(P_ATM, 1 * P_inlet_pa, 100)
        
        # Calculate Fanno flow for each outlet pressure
        q_fanno = []
        q_isothermal = []
        q_isothermal_simp = []
        
        for P_out in P_outlet_range:
            # Fanno flow
            P_inlet_gauge_psi = (P_inlet_pa - P_ATM) / 6894.76
            res = compute_flow(diameter_mm=fixed_diameter_mm, length_m=fixed_length,
                             P_inlet_psi=P_inlet_gauge_psi, P_outlet_pa=P_out)
            q_fanno.append(res['Q_std'] if 'Q_std' in res else np.nan)
            
            # Isothermal flow
            q_iso = compute_isothermal_flow(diameter_mm=fixed_diameter_mm, length_m=fixed_length,
                                           P_inlet_pa=P_inlet_pa, P_outlet_pa=P_out, f=0.021)
            q_isothermal.append(q_iso)

            D = fixed_diameter_mm / 1000.0  # m
            A = np.pi * (D / 2)**2    # m²
            # m_dot = A * np.sqrt((P_inlet_pa**2 - P_out**2) / (R * T0_K * (f * fixed_length / D + 2 * np.log(P_in/P_ATM))))
            # Q_std = m_dot / RHO_STD
            Q_max = A * np.sqrt((P_inlet_pa**2 - P_ATM**2) / (R * T0 * (f * fixed_length / D + 2 * np.log(P_inlet_pa / P_ATM)))) / RHO_STD
            q_approx = Q_max * np.sqrt(1 - ((P_out-P_ATM) / (P_inlet_pa-P_ATM))**2)
            q_isothermal_simp.append(q_approx)
            # print(Q_std)
        
        # Convert outlet pressure to psi for plotting
        P_outlet_psi = (P_outlet_range) / 6894.76
        
        # Plot Fanno flow
        plt.plot(P_outlet_psi, q_fanno, '-', color=color, linewidth=2, 
                label=f'Fanno, P_in={inlet_psi} psi')
        # Plot isothermal flow
        plt.plot(P_outlet_psi, q_isothermal, '--', color=color, linewidth=2,
                label=f'Isothermal, P_in={inlet_psi} psi')
        # Plot isothermal flow
        plt.plot(P_outlet_psi, q_isothermal_simp, ':', color=color, linewidth=5,
                label=f'simp, P_in={inlet_psi} psi')
    
    plt.xlabel('Outlet Pressure (psi)', fontsize=12)
    plt.ylabel('Volumetric Flow Rate (m$^3$/s)', fontsize=12)
    plt.title(f'Flow Rate vs Outlet Pressure: {D}m ID Tube, L={fixed_length}m', fontsize=14)
    plt.grid(True, alpha=0.3)
    plt.legend(title='Model & Inlet Pressure', fontsize=9, loc="upper right")
    plt.tight_layout()
    plt.axvline(P_ATM/ 6894.76, color='k')
    plt.xlim(0,None)
    plt.show()

    