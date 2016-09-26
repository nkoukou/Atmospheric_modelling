'''
This module reads libradtran output and calculates material entropy.
'''

import numpy as np
import matplotlib.pylab as plt
import matplotlib.ticker as mtk
import scipy.interpolate as sci
from glob_ent import find_nans

# Physical constants
c=2.998e8       # m s^-1
kb=1.38e-23     # kg m^2 s^-2 K^-1
h=6.626e-34     # J s = kg m^2 s^-1
sb=5.670e-8     # W m^-2 K^-4 = kg s^-3 K^-4
cp=1005         # J kg^-1 K^-1 = m^2 s^-2 K^-1 (specific cp of air)
sid=60*60*24.0  # sec (seconds in a day)
pi = np.pi      # sr (solid angle assumed for isotropically diffused radiation)
omega0=6.87e-5  # sr (solid angle subtended by the Sun)

# Load data
def load_output(filename, radtype='sw', only_output=False):
    '''
    Reads libradtran output file. The physical quantities are:
    
    - wvl/wvn (wavelength, nm converts to wavenumber, m^-1)
    - z (altitude, km converts to m)
    - T (temperature, K)
    - rho_air (air density, kg m^-3)
    - edir (direct flux, W m^-2 nm^-1 converts to W m^-2 m) !!! kurudz has mW??
    - edn (upwards diffuse flux, same as edir)
    - eup (downwards diffuse flux, same as edir)
    - heat (heating rate, K day^-1 nm^-1 converts to K day^-1 m)
    '''
    fdir = "libradtran/{0}.out".format(filename)
    output = np.loadtxt(fdir, comments='#')
    znum = np.count_nonzero(output[:,0]==output[:,0][0])
    
    wvl = output[:,0][::znum]
    wvn = 1.0e9/wvl
    z = output[:,1][:znum]*1000
    T = output[:,2][:znum]
    rho_air = output[:,3][:znum]
    
    output = output[:,4:].reshape(len(wvl), znum, 4)
    units = 1.0e-9*wvl[:,None]*wvl[:,None]
    edir = output[:,:,0] * units
    edn = output[:,:,1] * units
    eup = output[:,:,2] * units
    heat = output[:,:,3] * units
    
    if only_output: return edir, edn, eup, heat 
    return wvn, z, T, rho_air, edir, edn, eup, heat

# Math and physics conversion functions
def ent_flux(wvn, rad, radtype='sw', angle='dir'):
    '''
    Converts intensity to entropy flux with units W m^-2 m K^-1.
    
    Taylor approximation is used as in ent_datasets.py.
    '''
    if angle=='dir': ang = omega0
    elif angle=='diff': ang = pi
    intens = rad/ang
    wvn = wvn[:,None]
    
    y = intens/(2*h*c*c*wvn**3)
    np.seterr(all='ignore')
    ent1 = np.where(y>=0.01, (1+y)*np.log(1+y), (1+y)*(y - y*y/2 + y**3/3))
    # Since y > -1e10, all y < 0 are converted to 0 in ent2
    ent2 = np.where(y>0.0, -y*np.log(y), 0.0) 
    ent = np.where(y!=0.0, 2*kb*c*wvn*wvn*(ent1+ent2)*ang, 0.0)
    np.seterr(all='warn')
    return ent

def deriv(z, rad):
    '''
    Evaluates derivative of radiation flux or entropy with respect to altitude 
    using B-splines (1D z array and 2D rad array).
    '''
    derv=np.zeros(rad.shape)
    for i in range(rad.shape[0]):
        tck = sci.splrep(z, rad[i,:])
        derv[i,:] = sci.splev(z, tck, der=1)
    return derv

def spect_int(wvn, rad):
    '''
    Evaluates the spectral integral of given radiation flux or entropy over 
    given wavenumber range (1D wvn array and 2D rad array).
    '''
    intg = np.zeros(rad.shape[1])
    for i in range(rad.shape[1]):
        intg[i] = -np.trapz(rad[:,i], wvn)
    return intg

# Analysis
def heat_check(z, rho_air, edir, edn, eup):
    '''
    Estimates the libradtran heat input in units K day^-1 m for comparison.
    '''
    const = sid/cp/rho_air[None,:]
    check = (deriv(z, edir)+deriv(z, edn)+deriv(z, eup))*const
    return check

def sdot_calc(quants, radtype='sw', debug=False):
    '''
    Returns material, radiation and total entropy rates and a heat check.
    Entropy rates are in units W m^-3 K^-1 m.
    
    Parameter quants is the output of the load_output function when 
    only_output=False.
    '''
    wvn, z, T, rho_air, edir, edn, eup, heat = quants
    ent_dir = ent_flux(wvn, edir, radtype=radtype, angle='dir')
    ent_dn = ent_flux(wvn, edn, radtype=radtype, angle='diff')
    ent_up = ent_flux(wvn, eup, radtype=radtype, angle='diff')
    
    sdotmat = cp/sid * rho_air[None,:]/T[None,:] * heat
    sdotrad = deriv(z, ent_up) - deriv(z, ent_dn) - deriv(z, ent_dir)
    sdot = sdotmat + sdotrad
    check = heat_check(z, rho_air, edir, edn, eup)
    
    if debug: # !!!
        print ent_dn.size,'\n'
        print 'ent_dir', len(ent_dir[ent_dir==0])#, ' / ', len(edir[edir<=0])
        print '--------------------'
        print 'ent_dn', len(ent_dn[ent_dn==0])
        print '--------------------'
        print 'ent_up', len(ent_up[ent_up==0])
        print '--------------------'
        print 'sdotrad', len(sdotrad[sdotrad<0])
        print sdotrad
    
    return sdotmat, sdotrad, sdot, check

# Plots - to be used only via the flux_output function
def _plot_vertical(z, quant, tu):
    '''
    Plots a spectrally integrated quantity over all altitudes.
    
    Parameter tu is a tuple of titles and units to associate with the quants. 
    It is provided when the function runs from within flux_output().
    '''
    ts, us = tu
    fig = plt.figure()
    plt.plot(z/1000, ts[quant])
    ax.set_title('{0}'.format(quant))
    plt.xlabel('$z\ (km)$')
    plt.ylabel('${0}\ {1}$'.format(quant, us[quant]))

def _plot_levels(wvn, z, quants, tu, levels=[25]):
    '''
    Plots given quantities (e.g. [edir, eup, edn]) at given altitude levels 
    (0-25) over all wavenumbers. Every plot displays all quants at a specific 
    level. If only one quant is provided it is plotted on one plot for all 
    levels.
    
    Parameter tu is a tuple of titles and units to associate with the quants. 
    It is provided when the function runs from within flux_output().
    '''
    if quants==[]: return
    ts, us = tu
    
    if len(quants)==1:
        ax = fig.add_subplot(1,1,1)
        for lev in levels:
            ax.plot(wvn, ts[quants[0]][:,lev], label='{0:.3f} km'
                    .format(z[lev]/1000))
        ax.set_xlabel('$Wavenumber (m^{-1})$')
        ax.set_ylabel('${0}\ {1}$'.format(quants[0], us[quants[0]]))
        ax.yaxis.set_major_formatter(mtk.FormatStrFormatter('%.2f'))
        ax.legend(loc='upper right')
    else:
        fig = plt.figure()
        #fig.suptitle('')
        for lev in levels:
            ax = fig.add_subplot(len(levels),1, levels.index(lev)+1)
            for j in range(len(quants)):
                ax.plot(wvn, ts[quants[j]][:,lev], label='{0}'
                        .format(quants[j]))
            ax.set_title('Altitude {0:.3f} km'.format(z[lev]/1000))
            ax.set_xlabel('$Wavenumber\ (m^{-1})$')
            ax.set_ylabel('${0}$'.format(us[quants[0]]))
            ax.yaxis.set_major_formatter(mtk.FormatStrFormatter('%.2f'))
            ax.legend(loc='upper right')
            plt.tight_layout()

# Export output
def flux_output(filename, radtype='sw', z_plots=[], lev_plots=[], levels=[0,25]):
    '''
    Exports flux output into a .txt file.

    F - radiation flux integrated over wavelength
    J - entropy flux integrated over wavelength
    Q - heat
    sdot - entropy rate
    
    Parameters z_plots and lev_plots indicate what plots to be made against 
    altitude and wavelength respectively. The titles of spectrally integrated 
    quantities should be in the z_plots list (e.g. 'Q' or 'sdot'), while the 
    titles of either entropy or radiation irradiances (e.g. 'edir', 'eup' and 
    'edn' for radiation) should be in lev_plots list. 
    
    ts, us and us_ltx are dictionaries mapping titles to corresponding 
    quantities, units and units in latex format respectively.
    
    !!! atm reaches 38km
    '''
    # Load quantities
    quants = load_output(filename, radtype=radtype, only_output=False)
    wvn, z, T, rho_air, edir, edn, eup, heat = quants
    sdots = sdot_calc(quants, radtype=radtype, debug=False)
    entdir = ent_flux(wvn, edir, radtype=radtype, angle='dir') 
    entup = ent_flux(wvn, eup, radtype=radtype, angle='diff')   
    entdn = ent_flux(wvn, edn, radtype=radtype, angle='diff')
    Fdir = spect_int(wvn, edir)
    Fup = spect_int(wvn, eup)
    Fdn = spect_int(wvn, edn)
    Jdir = spect_int(wvn, entdir)
    Jup = spect_int(wvn, entup)
    Jdn = spect_int(wvn, entdn)
    sdot = spect_int(wvn, sdots[2])
    sdotr = spect_int(wvn, sdots[1])
    sdotm = spect_int(wvn, sdots[0])
    Q = spect_int(wvn, heat)
    Qcheck = spect_int(wvn, sdots[3])
    
    # Make dictionaries
    ts = {'z':z, 'edir':edir, 'eup':eup, 'edn':edn, 'entdir':entdir, 
          'entup':entup, 'entdn':entdn, 'Fdir':Fdir, 'Fup':Fup, 
          'Fdn':Fdn, 'Jdir':Jdir, 'Jup':Jup, 'Jdn':Jdn, 
          'sdot':sdot, 'sdotr':sdotr, 'sdotm':sdotm, 'Q':Q, 'Qcheck':Qcheck}
    us = {'z':'(m)', 'edir':'(W m-2 m)', 'eup':'(W m-2 m)', 'edn':'(W m-2 m)', 
          'entdir':'(W m-2 K-1 m)', 'entup':'(W m-2 K-1 m)', 
          'entdn':'(W m-2 K-1 m)', 'Fdir':'(W m-2)', 'Fup':'(W m-2)', 
          'Fdn':'(W m-2)', 'Jdir':'(W m-2 K-1)', 'Jup':'(W m-2 K-1)', 
          'Jdn':'(W m-2 K-1)', 'sdot':'(W m-3 K-1)', 'sdotr':'(W m-3 K-1)', 
          'sdotm':'(W m-3 K-1)', 'Q':'(K day-1)', 'Qcheck':'(K day-1)'}
    us_ltx = {'z':'(m)', 'edir':'(W\ m^{-2}\ m)', 'eup':'(W\ m^{-2}\ m)', 
              'edn':'(W\ m^{-2}\ m)', 'entdir':'(W\ m^{-2}\ K^{-1}\ m)', 
              'entup':'(W\ m^{-2}\ K^{-1}\ m)', 
              'entdn':'(W\ m^{-2}\ K^{-1}\ m)', 'Fdir':'(W\ m^{-2})', 
              'Fup':'(W\ m^{-2})', 'Fdn':'(W\ m^{-2})', 
              'Jdir':'(W\ m^{-2}\ K^{-1})', 'Jup':'(W\ m^{-2}\ K^{-1})', 
              'Jdn':'(W\ m^{-2}\ K^{-1})', 'sdot':'(W\ m^{-3}\ K^{-1})', 
              'sdotr':'(W\ m^{-3}\ K^{-1})', 'sdotm':'(W\ m^{-3}\ K^{-1})', 
              'Q':'(K\ day^{-1})', 'Qcheck':'(K\ day^{-1})'}
    #z_plot = ['Fdir', 'Fup', 'Fdn', 'Jdir', 'Jup', 'Jdn', 'sdot', 'sdotr', 
    #          'sdotm', 'Q', 'Qcheck']
    
    # Make plots
    for zplot in z_plots:
        _plot_vertical(z, quant=zplot, tu=(ts,us_ltx))
    _plot_levels(wvn, z, quants=lev_plots, tu=(ts,us_ltx), levels=levels)
    
    # Write material entropy
    out = open("libradtran/entropy_budget_{0}.txt".format(radtype), 'w')
    out.write('{0:>9} {1:>11} {2:>11} {3:>11} {4:>11} {5:>11} {6:>11} ' \
              '{7:>11} {8:>11} {9:>11} {10:>11} {11:>11}\n'
              .format('z ', 'Fdir ', 'Fup ', 'Fdn ', 'Jdir ', 'Jup ', \
              'Jdn ', 'sdot ', 'sdotr ', 'sdotm ', 'Q ', 'Qcheck '))
    out.write('{0:>9} {1:>11} {2:>11} {3:>11} {4:>11} {5:>11} {6:>11} ' \
              '{7:>11} {8:>11} {9:>11} {10:>11} {11:>11}\n'
              .format(us['z'], us['Fdir'], us['Fup'], us['Fdn'], us['Jdir'], \
              us['Jup'], us['Jdn'], us['sdot'], us['sdotr'], us['sdotm'], \
              us['Q'], us['Qcheck']))
    for i in range(len(z)):
        out.write('{0:>9.3f} {1:>11.2E} {2:>11.2E} {3:>11.2E} {4:>11.2E} ' \
                  '{5:>11.2E} {6:>11.2E} {7:>11.2E} {8:>11.2E} {9:>11.2E} ' \
                  '{10:>11.2E} {11:>11.2E}\n'
                  .format(z[i], Fdir[i], Fup[i], Fdn[i], Jdir[i], Jup[i], \
                  Jdn[i], sdot[i], sdotr[i], sdotm[i], Q[i], Qcheck[i]))
    
    rad = Jup[0]-Jdn[0]-Jdir[0]
    mat = -(Fup[0]-Fdn[0]-Fdir[0])/T[0]
    sfc = rad + mat
    out.write('\nSfc ent (W m-2 K-1): rad = {0:.3E}, mat = {1:.3E}, ' \
              'net = {2:.3E}'.format(rad, mat, sfc))
    rad = np.trapz(sdotr, z)
    mat = np.trapz(sdotm, z)
    atm = rad + mat
    out.write('\nAtm ent (W m-2 K-1): rad = {0:.3E}, mat = {1:.3E}, ' \
              'net = {2:.3E}'.format(rad, mat, atm))
    toaup = Jup[-1]
    toadir = -Jdir[-1]
    toa = Jup[-1]-Jdir[-1]
    out.write('\nTOA ent (W m-2 K-1):  up = {0:.3E}, dir = {1:.3E}, ' \
              'net = {2:.3E}'.format(toaup, toadir, toa))
    net = toa - sfc - atm
    out.write('\n\nNet material entropy: {0:.3E} (W m-2 K-1)'.format(net))
    out.close()
    
    # Write TOA
    toa = open("libradtran/entropy_budget_toa_{0}.txt".format(radtype), 'w')
    toa.write('{0:>8} {1:>13} {2:>13} {3:>13} {4:>13}\n'
              .format('wvl ', 'eup ', 'edir ', 'entup ', 'entdir '))
    toa.write('{0:>8} {1:>13} {2:>13} {3:>13} {4:>13}\n'
              .format('(nm)', us['eup'], us['edir'], us['entup'], us['entdir']))
    for i in range(len(wvn)):
        toa.write('{0:>8.3f} {1:>13.3E} {2:>13.3E} {3:>13.3E} {4:>13.3E}\n'
              .format(1.0e9/wvn[i], eup[i,-1], edir[i,-1], entup[i,-1], \
              entdir[i,-1]))
    toa.write('\n{0:>8} {1:>13.3E} {2:>13.3E} {3:>13.3E} {4:>13.3E}\n'
              .format('spec_int', Fup[-1], Fdir[-1], Jup[-1], Jdir[-1]))
    toa.close()

flux_output('0solar_rep', radtype='sw', z_plots=['sdotr','sdotm'], lev_plots=['entdir','entup','entdn'], levels=[0,25])
plt.show()






