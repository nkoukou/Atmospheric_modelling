'''
This module converts radiation intensity datasets to radiation and entropy flux
datasets.
'''

import numpy as np

# Load datasets
wvlen = np.load('datasets/wvlen.npy')           # nm
wvlen_lres = np.load('datasets/wvlen_lres.npy') # nm
wvnum = np.load('datasets/wvnum.npy')           # cm^-1
wvlen_num = 1.0e7/wvnum                         # nm

# Physical constants
c=2.998e8   # m s^-1
kb=1.38e-23 # kg m^2 s^-2 K^-1
h=6.626e-34 # J s = kg m^2 s^-1

def loadrad(month, lc=False):
    '''
    Loads SW and LW radiation datasets which correspond to given month.
    Parameter month must be of the form 'yymm' (e.g. '0001' corresponds
    to year 2000, month 01).
    
    SW radiation is corrected by a factor of 1000.
    '''
    if not lc:
        sw = 1000*np.load('datasets/sw%s.npy' % (month)) # uW cm^-2 sr^-1 nm^-1
        lw = np.load('datasets/lw%s.npy' % (month))      # W cm^-2 sr^-1 cm
    elif lc:
        sw = np.load('datasets/lres_sw%s.npy' % (month)) # uW cm^-2 sr^-1 nm^-1
        lw = np.load('datasets/clr_lw%s.npy' % (month))  # W cm^-2 sr^-1 cm
    return sw, lw

# Conversion functions
def radtorad(rad,radtype='sw'):
    '''
    Converts radiation to units W m^-2 sr^-1 nm^-1
    '''
    if radtype=='sw':
        rconst = 1.0e-2
    elif radtype=='lw':
        rconst = 1.0e-3*wvnum*wvnum
        rconst = rconst[:,None,None]
    return rconst*rad

def radtoent(rad,radtype='sw',lc=True):
    '''
    Converts array of radiation intensity to array of entropy.
    
    Needs radiation in W m^-2 sr^-1 m.
    Returns entropy in mW m^-2 sr^-1 K^-1 nm^-1.
    '''
    if radtype=='sw':
        if not lc: wvl = wvlen
        elif lc: wvl = wvlen_lres[::-1]
        iconst = 1.0e-11*wvl*wvl
        iconst = iconst[:,None,None]
    elif radtype=='lw':
        wvl = wvlen_num
        iconst = 1.0e2
    wvn = 1.0e9/wvl
    econst = 1.0e-6*wvn*wvn
    econst, wvn = econst[:,None,None], wvn[:,None,None]
    
    intens = iconst*rad
    y = intens/(2*h*c*c*wvn**3)
    
    np.seterr(all='ignore')
    ent1 = np.where(y>=0.01, (1+y)*np.log(1+y), (1+y)*(y - y*y/2 + y**3/3))
    ent2 = -y*np.log(y)
    np.seterr(all='warn')
    ent = np.where(y!=0.0, econst*2*kb*c*wvn*wvn*(ent1+ent2), 0.0)
    return ent

def rad_flux(rad,radtype='sw',lc=True):
    '''
    Integrates radiation over wavelength to get radiative flux.
    The units are W m^-2 sr^-1.
    '''
    if radtype=='sw':
        if not lc: wvl = wvlen
        elif lc: wvl = wvlen_lres[::-1]
    elif radtype=='lw':
        wvl = wvlen_num
    n = len(wvl)-1
    wvl = wvl[:,None,None]
    rad = radtorad(rad,radtype)
    
    flux = rad[0]*(wvl[0]-wvl[1])+rad[n]*(wvl[n-1]-wvl[n])
    for i in range(1,n-1):
        flux += 0.5*rad[i]*(wvl[i-1]-wvl[i+1])
    return flux

def ent_flux(rad,radtype='sw',lc=True):
    '''
    Integrates entropy over wavelength to get radiative flux.
    The units are mW m^-2 sr^-1 K^-1.
    '''
    if radtype=='sw':
        if not lc: wvl = wvlen
        elif lc: wvl = wvlen_lres[::-1]
    elif radtype=='lw':
        wvl = wvlen_num
    n = len(wvl)-1
    wvl = wvl[:,None,None]
    ent = radtoent(rad,radtype,lc)
    
    flux = ent[0]*(wvl[0]-wvl[1])+ent[n]*(wvl[n-1]-wvl[n])
    for i in range(1,n-1):
        flux += 0.5*ent[i]*(wvl[i-1]-wvl[i+1])
    return flux

def flux_month(month, re='r', lc=False):
    sw_rad, lw_rad = loadrad(month, lc)
    if re=='r':
        sw = rad_flux(sw_rad,'sw')
        lw = rad_flux(lw_rad,'lw')
    elif re=='e':
        sw = ent_flux(sw_rad,'sw')
        lw = ent_flux(lw_rad,'lw')
    return sw, lw

def months_in_year(year):
    yr = str(year)[-2:]
    months = []
    for m in range(1,13):
        if m<10: mstr = '0'+str(m)
        else: mstr = str(m)
        months.append(yr+mstr)
    return months

def export_all(yr, lc=False):
    for m in months_in_year(yr):
        swr, lwr = flux_month(m,'r', lc)
        print 'RAD %s' % (m)
        swe, lwe = flux_month(m,'e', lc)
        if not lc: spre,lpre='',''
        elif lc: spre,lpre='lres_','clr_'
        np.save('datasets/flux/'+spre+'swr'+m, swr)
        np.save('datasets/flux/'+lpre+'lwr'+m, lwr)
        np.save('datasets/flux/'+spre+'swe'+m, swe)
        np.save('datasets/flux/'+lpre+'lwe'+m, lwe)
        print 'DONE %s' % (m)




