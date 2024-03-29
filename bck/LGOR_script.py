from scipy.optimize import differential_evolution
import numpy as np
import pandas as pd
import os, sys
from collections import defaultdict

class PVTCORR:
    def __init__(self, sat_pressure, Tsp, Psp, filepath):
        self.sat_pressure = sat_pressure
        self.Tsp = Tsp
        self.Psp = Psp
        self.Salinity = 20000
        self.LARGE       = 1e+12
        self.TINY        = 1e-12
        self.iterMax     = 100
        self.Pstd = 14.69
        self.Tstd = 60
        self.AirMolecularWt = 28.96

        if not os.path.exists(filepath):
            print('PVT file does not exist:%s'%(filepath))
            sys.exit(1)
        self.pvt_table = pd.read_csv(filepath)

    def _computeGasGravityAtSeperatorConditions(self,Gamma, API):
        Gamma_gs = Gamma * (1.0 + 5.912e-5 * API * self.Tsp * np.log10(self.Psp / 114.7))
        return Gamma_gs

    def _computeIsothermalLiveOilCompressibilityAbovePsat(self,api, temperature,
                                                         pressure, gas_gravity):
        Tres = temperature
        API = api
        Gamma_gs = self._computeGasGravityAtSeperatorConditions(gas_gravity, API)
        GOR = self._computeSolutionGasOilRatio(api,temperature,self.sat_pressure,
                                              gas_gravity)
        Co = (-1433.0 + 5.0 * GOR + 17.2 * Tres - 1180.0 * Gamma_gs
              + 12.61 * API) / (pressure * 1e+5)
        return Co

    def _computeSolutionGasOilRatio(self, api, temperature,
                                   pressure, gas_gravity):
        # Vazquez and Beggs, 1980 (Default in EMPower)
        C1 = 0.0362
        C2 = 1.0937
        C3 = 25.7240
        if (api > (30.0 + 1e-12)):
            C1 = 0.0178
            C2 = 1.1870
            C3 = 23.9310
        Psat = self.sat_pressure
        Tsat = temperature
        API = api
        Gamma_gs = self._computeGasGravityAtSeperatorConditions(gas_gravity,API)
        a = C1 * Gamma_gs
        c = np.exp(C3 * API / (Tsat + 459.67))
        if pressure <= Psat:
            temp = a * (np.power(pressure, C2)) * c
        else:
            temp = a * (np.power(self.sat_pressure, C2)) * c
        return temp

    def _computeLiveOilFVF(self, api, temperature, pressure,  gas_gravity):

        C1 = 4.677e-4
        C2 = 1.751e-5
        C3 = -1.811e-8
        if (api > (30.0 + 1e-12)):
            C1 = 4.670e-4
            C2 = 1.100e-5
            C3 = 1.337e-9

        Psat = self.sat_pressure
        Tres = temperature
        API = api
        Gamma_gs = self._computeGasGravityAtSeperatorConditions(gas_gravity,API)
        # print(Gamma_gs)
        C1 = C1 * 1.0
        C2 = C2 * (Tres - 60) * (API / Gamma_gs)
        C3 = C3 * (Tres - 60) * (API / Gamma_gs)
        Rso = self._computeSolutionGasOilRatio(api, temperature, pressure,
                                              gas_gravity)
        if pressure <= Psat:
            temp = 1.0 + C1 * Rso + C2 + C3 * Rso
        else:
            Co = self._computeIsothermalLiveOilCompressibilityAbovePsat(api,
               temperature, pressure, gas_gravity)
            # print(Co)
            Rso_sat = self._computeSolutionGasOilRatio(api, temperature,
                                                      self.sat_pressure,
                                                      gas_gravity)
            # print(Rso_sat)
            Bo_sat = 1.0 + C1 * Rso_sat + C2 + C3 * Rso_sat
            # print(Bo_sat)
            temp = Bo_sat * np.exp(-Co * (pressure - Psat))
        return temp

    def computeLiveOilViscosity(self,api, temperature, pressure, gas_gravity):

        # Beggs and Robinson, 1975 Defailt EMPower
        Rso = self._computeSolutionGasOilRatio(api, temperature, pressure,
                                              gas_gravity)
        Visc_oil = self.computeDeadOilViscosity(api, temperature)
        a             = 10.715*((Rso + 100.0)**(-0.515))
        b             = 5.44*  ((Rso + 150.0)**(-0.338))
        Visc_oil = a*(Visc_oil**b)
        #self.computeLiveOilViscosityAboveBubblePt(regionNum)
        return Visc_oil

    # def computeLiveOilViscosityAboveBubblePt(self, pressure):
    #     """
    #     Parameters
    #     ----------
    #     regionNum : Integer
    #     """
    #         # Vazques and Beggs, 1980
    #             # Below is EMPower formulation
    #     m = 2.6 * (pressure[indx] ** 1.187) * np.exp(-11.513 - 8.98e-5 * pressure[indx])
    #     Visc_oil = Visc_oil_sat[regionNum] * (
    #                 self.Pressure[indx] * 1.0 / self.Psat[regionNum]) ** m

    def computeDeadOilViscosity(self, api, temperature):

        # Beggs and Robinson, 1975 Default EMPower
        b             = np.exp(6.9824 - 0.04658 * api)
        a             = b*(temperature**(-1.163))
        Visc_oil = 10**a - 1
        return Visc_oil

    def computeDryGasFVF(self, pressure, temperature, gas_gravity):

        self.computeDryGasZFactor(pressure, gas_gravity, temperature)
        Tres = temperature
        fac = self.Pstd/(self.Tstd + 459.67) # use this fro ft3/scf
        fac = fac*0.178107607 # conversion factor for cubic feet to bbl for us crude oil http://www.asknumbers.com/CubicFeetToBarrel.aspx
        Bg = fac*self.Zfactor*(Tres + 459.67)/pressure
        return Bg

    def computeDryGasZFactor(self,pressure, gas_gravity, temperature):

        # Dranchuk and Abou-Kassem, 1975-Default EMPower
        Zr                      = 1.0
        Zfactor = Zr
        A1       = 0.3265
        A2       =-1.0700
        A3       =-0.5339
        A4       = 0.01569
        A5       =-0.05165
        A6       = 0.5475
        A7       =-0.7361
        A8       = 0.1844
        A9       = 0.1056
        A10      = 0.6134
        A11      = 0.7210

        error= self.LARGE
        iter = 0
        Ppc = 756.8 - 131.0 * gas_gravity - 3.60 * (gas_gravity ** 2.0)
        Tpc = 169.2 + 349.5 * gas_gravity - 74.0 * (gas_gravity ** 2.0)
        Tpr  = (temperature + 459.67)/Tpc
        Ppr  = pressure/Ppc
        Rpr  = 0.27*Ppr/(Zfactor*Tpr)
        assert Tpr >= 1.0 and Tpr <= 3.0,  'Pseudo Reduced Temperature, Tpr: ' + str(Tpr) + ' is Out Of Bounds: 1.0 <= Tpr <=3.0'
        #assert Ppr >= 0.2 and Ppr <= 30.0, 'Pseudo Reduced Pressure   , Ppr: ' + str(Ppr) + ' for Region: ' + str(regionNum) + ' is Out Of Bounds: 0.2 <= Ppr <=30.0'
        # Newton Raphson to evaluate Density
        while(error > self.TINY and iter < self.iterMax):
            #Note: Tpc is computed in Rankine according to correlation
            #Starling-Carnahan equation of state
            # 1.0 <= Tpr <=3.0
            # 0.2 <= Ppr <= 30.0 and
            Rpr_Old = Rpr
            a       = (A1 + A2/Tpr + A3/(Tpr**3) + A4/(Tpr**4) + A5/(Tpr**5))
            b       = 0.27*Ppr/Tpr
            c       = A6 + A7/Tpr + A8/(Tpr**2)
            d       = A9*(A7/Tpr + A8/(Tpr**2))
            e       = A10/(Tpr**3)
            Zr      = 1.0 + a * Rpr - b / Rpr + c * (Rpr**2) - d * (Rpr**5) + e * (1 + A11*(Rpr**2)) * (Rpr**2) * np.exp(-A11 * (Rpr ** 2))
            Zprime  = a + b / (Rpr**2) + 2 * c * Rpr - 5 * d * (Rpr**4) + 2 * e * Rpr * np.exp(-A11 * (Rpr ** 2)) * (1 + 2 * A11 * (Rpr ** 3) - A11 * (Rpr ** 2) * (1 + A11 * (Rpr ** 2)))
            Rpr     = Rpr_Old - Zr/Zprime
            error   = np.fabs(Rpr - Rpr_Old)
            iter   += 1
        Zr = 0.27*Ppr/(Rpr*Tpr)
        assert Zr > 0.0, 'Error in Compressibility Computation '  'error: ' + str(error) + ' iter: ' + str(iter) + ' Zr: ' + str(Zr) +' pressure: ' + str(pressure)
        self.Zfactor = Zr

    def computeDryGasViscosity(self, temperature, pressure, gas_gravity):
        self.computeDryGasZFactor(pressure, gas_gravity, temperature)
        GasMa = self.AirMolecularWt * gas_gravity
        GasDensity = self.computeDryGasDensity(GasMa, temperature, pressure)
        Mg = GasMa
        A = (9.379 + 0.01607*Mg)*(temperature+ 459.67)**1.5/(209.2 + 19.26*Mg + (temperature+ 459.67))
        B = 3.448 + (986.4/(temperature+ 459.67)) + 0.01009*Mg
        C = 2.447 - 0.2224*B
        Visc_gas = A * 1e-4 * np.exp(B * (GasDensity ** C))
        return Visc_gas

    def computeDryGasDensity(self, GasMa, temperature, pressure):
        GasConstant = 10.73
        FarToRankine = 459.67
        lbFt3ToGmCc = 1 / 62.428
        fac = GasMa/GasConstant*lbFt3ToGmCc
        # Den = Ma*P/ZRT
        GasDensity = fac*pressure/(self.Zfactor*(temperature + FarToRankine))
        return GasDensity

    def computeWaterFVF(self, temperature, pressure):
        dVwp = -1.95301e-9 * temperature * pressure - 1.72834e-13 * temperature * (
                    pressure ** 2) - 3.58922e-7 * pressure - 2.25341e-10 * (pressure ** 2)
        dVwt  = -1.0001e-2 + 1.33391e-4*temperature + 5.50654e-7*(temperature**2)
        Pctrl = self.sat_pressure
        if pressure <= Pctrl:
            Bw = (1.0 + dVwt) * (1.0 + dVwp)
        else:
            Cw = self.computeIsothermalWaterCompressiblity(pressure, temperature)
            Bwb = (1.0 + dVwt) * (1.0 + dVwp)
            Bw = Bwb / (1.0 + Cw * (pressure - Pctrl))
        return Bw
        # if self.FluidType[regionNum] != 'Drygas':
        #     self.computeWaterFVFAboveBubblePt(regionNum)

    def computeIsothermalWaterCompressiblity(self, pressure, temperature):
        # cw = Isothermal water (brine) compressibility, psi-1
        # Pr = Reservoir pressure, psia
        # S = Salinity, mg/L, Cs (Cs = denw(sc) * Cppm), Cppm = Dissolved solids parts per million (Cppm = Cw *10^4)
        # Tr = Reservoir temperature, F
        # denw(sc) = Water density at standard conditions, gm/cc
        # Osif, 1988 - Default
        sal = self.Salinity * 1e-4
        WaterDensity_sc = (62.368 + 0.438603*sal + 1.60074*1e-3*(sal**2))/62.428
        salinity = self.Salinity * WaterDensity_sc
        Cw = 1.0 / (7.033 * pressure + 0.5415 * salinity - 537.0 *
                         temperature + 403300.0)
        return Cw

    def computerWaterViscosity(self, pressure, temperature):
        Sal = self.Salinity * 1e-4
        A = 109.574 - 8.40564 * Sal + 0.313314 * (Sal ** 2) + 8.72213 * 1e-3 * (Sal ** 3)
        B = 1.12166 - 2.63951 * 1e-2 * Sal + 6.79461 * 1e-4 * (Sal ** 2) + 5.47119 * 1e-5 * (
                    Sal ** 3) - 1.55586 * 1e-6 * (Sal ** 4)
        Visc_water_sc = A * (temperature ** (-B))
        Visc_water = Visc_water_sc * (
                        0.9994 + 4.0295 * 1e-5 * pressure + 3.1062 * 1e-9 * (pressure ** 2))
        return Visc_water

    def _optimizer(self, X):
        p_array = np.array(self.pvt_table['p'])
        bo_array = np.array(self.pvt_table['Bo'])
        bg_array = np.array(self.pvt_table['Bg'])
        bw_array = np.array(self.pvt_table['Bw'])
        rgo_array = np.array(self.pvt_table['Rgo'])
        Visc_oil_array = np.array(self.pvt_table['visc_o'])
        Visc_gas_array = np.array(self.pvt_table['visc_g'])
        Visc_water_array = np.array(self.pvt_table['visc_w'])
        obj = 0.
        for p, bo, bg, bw, rgo, vo, vg, vw in zip(p_array, bo_array, bg_array,
                                                  bw_array, rgo_array, Visc_oil_array,
                              Visc_gas_array, Visc_water_array):
                Rso = self._computeSolutionGasOilRatio(X[0], X[2], p, X[1]) - rgo
                Bo = self._computeLiveOilFVF(X[0], X[2], p, X[1]) - bo
                Bg = self.computeDryGasFVF(p, X[2], X[1]) - bg
                Bw = self.computeWaterFVF(X[2], p) - bw
                Visc_o = self.computeLiveOilViscosity(X[0], X[2], p, X[1]) - vo
                Visc_g = self.computeDryGasViscosity(X[2], p, X[1]) - vg
                Visc_w = self.computerWaterViscosity(p, X[2]) - vw
                obj+=(Bo/bo) ** 2 + (Bg/bg) ** 2 + (Bw/bw) ** 2 + (Rso/rgo) ** 2 + (Visc_o/vo)**2 + \
                     (Visc_g/vg)**2 + (Visc_w/vw)**2
                # obj+=(Bo/bo) ** 2 + (Bg/bg) ** 2  + (Rso/rgo) ** 2 + \
                #      (Visc_g/vg)**2 + (Visc_o/vo)**2
                # obj+=(Bo/bo) ** 2 + (Rso/rgo) ** 2
                # obj += (Rso / rgo) ** 2

        return obj

    def match_PVT_values(self, range_of_values, additional_details=False):
        res = differential_evolution(self._optimizer, range_of_values, seed=100, strategy='best2exp')
        if additional_details:
            print(res)
        return res.x

    def compute_PVT_values(self, api, gas_gravity, temperature):
        p_array = np.array(self.pvt_table['p'])
        bo_array = np.array(self.pvt_table['Bo'])
        bg_array = np.array(self.pvt_table['Bg'])
        bw_array = np.array(self.pvt_table['Bw'])
        rgo_array = np.array(self.pvt_table['Rgo'])
        Visc_oil_array = np.array(self.pvt_table['visc_o'])
        Visc_gas_array = np.array(self.pvt_table['visc_g'])
        Visc_water_array = np.array(self.pvt_table['visc_w'])
        comparison_dict = defaultdict(list)
        for p, bo, bg, bw, rgo, vo, vg, vw in zip(p_array, bo_array, bg_array, bw_array, rgo_array, Visc_oil_array,
                                          Visc_gas_array, Visc_water_array):
            rgo_c = self._computeSolutionGasOilRatio(api, temperature, p, gas_gravity)
            bo_c = self._computeLiveOilFVF(api, temperature, p, gas_gravity)
            bg_c = self.computeDryGasFVF(p, temperature, gas_gravity)
            bw_c = self.computeWaterFVF(temperature, p)
            Visc_o = self.computeLiveOilViscosity(api, temperature, p, gas_gravity)
            Visc_g = self.computeDryGasViscosity(temperature, p, gas_gravity)
            Visc_w = self.computerWaterViscosity(p, temperature)
            comparison_dict['Actual_Rgo'].append(rgo)
            comparison_dict['Calculated_Rgo'].append(rgo_c)
            comparison_dict['Actual_Bo'].append(bo)
            comparison_dict['Calculated_Bg'].append(bg_c)
            comparison_dict['Actual_Bg'].append(bg)
            comparison_dict['Calculated_Bw'].append(bw_c)
            comparison_dict['Actual_Bw'].append(bw)
            comparison_dict['Calculated_Bo'].append(bo_c)
            comparison_dict['Actual_vo'].append(vo)
            comparison_dict['Calculated_vo'].append(Visc_o)
            comparison_dict['Actual_vg'].append(vg)
            comparison_dict['Calculated_vg'].append(Visc_g)
            comparison_dict['Actual_vw'].append(vw)
            comparison_dict['Calculated_vw'].append(Visc_w)
            comparison_dict['pressure'].append(p)
        return comparison_dict

if __name__ == '__main__':
    sat_pressure = 5123.2
    pvtc  = PVTCORR(sat_pressure=sat_pressure, Tsp=60, Psp=500, filepath=r'D:\uncon_workflow\SOD\PLU28BS_127H_PVT.csv')
    ranges = [(50, 55), (0.85, 1), (130, 230)]
    api, gas_gravity, temperature = pvtc.match_PVT_values(ranges, additional_details=True)
    dct = pvtc.compute_PVT_values(api, gas_gravity, temperature)
    # dct = pvtc.compute_PVT_values(48.35,   0.817, 136.31)
    # dct = pvtc.compute_PVT_values(65.01, 1.0648, 237.28)
    df = pd.DataFrame(dct)
    df[df['pressure'] <= sat_pressure].to_csv('plu_PVT_500.csv')
    df[df['pressure'] <= sat_pressure].plot(x='pressure', y=['Actual_Rgo', 'Calculated_Rgo'],ylim=[0,6000])
    df[df['pressure'] <= sat_pressure].plot(x='pressure', y=['Actual_Bo','Calculated_Bo'],ylim=[0.5,3.5])
    df[df['pressure'] <= sat_pressure].plot(x='pressure', y=['Actual_Bg','Calculated_Bg'],ylim=[0,0.05])
    df[df['pressure'] <= sat_pressure].plot(x='pressure', y=['Actual_Bw','Calculated_Bw'],ylim=[0.5,1.5])
    df[df['pressure'] <= sat_pressure].plot(x='pressure', y=['Actual_vo','Calculated_vo'],ylim=[0,5])
    df[df['pressure'] <= sat_pressure].plot(x='pressure', y=['Actual_vg','Calculated_vg'],ylim=[0,0.1])
    df[df['pressure'] <= sat_pressure].plot(x='pressure', y=['Actual_vw','Calculated_vw'],ylim=[0,1])
    import matplotlib.pyplot as plt
    plt.show()