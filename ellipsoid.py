import numpy as np


from astropy.coordinates import SkyCoord
import astropy.coordinates as coord
from astropy import constants as const
from astropy import units as u
from astropy.time import Time
from astropy.table import Table, QTable
import os

from astroquery.gaia import Gaia
import argparse
import matplotlib.pyplot as plt


def queryGaia(var, gcns, num, save):
    # Retrieves data from Gaia archive
    # var = variable stars or all stars?
    # gcns = GCNS or all Gaia stars?
    # num = max number of stars to retrieve
    # save = save to a file? 
    
    if gcns == True:
        dist_col = 'dist_50'
        cartesian = True
        x_col, y_col, z_col = 'xcoord_50', 'ycoord_50', 'zcoord_50'
        ra_col, dec_col = 'ra', 'dec'
        dist84_col, dist16_col = 'dist_84', 'dist_16'
        gmag_col, bpmag_col, rpmag_col = 'phot_g_mean_mag', 'phot_bp_mean_mag', 'phot_rp_mean_mag'
        
        query_select = f'SELECT TOP {num} gcns.{dist_col}, gcns.{x_col}, gcns.{y_col}, gcns.{z_col}, \
                        gcns.{ra_col}, gcns.{dec_col}, gcns.{dist84_col}, gcns.{dist16_col}, \
                        gcns.{gmag_col}, gcns.{bpmag_col}, gcns.{rpmag_col}, gcns.source_id'
        if var == True:
            query = f'{query_select} \
            FROM gaiadr3.vari_summary AS var \
            JOIN external.gaiaedr3_gcns_main_1 AS gcns ON var.source_id=gcns.source_id'
            sf = 'GCNS_var.fits'
            
        elif var == False:
            query = f'{query_select} \
            FROM external.gaiaedr3_gcns_main_1 AS gcns'
            sf = 'GCNS.fits'
            
    elif gcns == False:
        dist_col = 'distance_gspphot'
        cartesian = False
        ra_col, dec_col = 'ra', 'dec'
        dist84_col, dist16_col = 'distance_gspphot_upper', 'distance_gspphot_lower'
        gmag_col, bpmag_col, rpmag_col = 'phot_g_mean_mag', 'phot_bp_mean_mag', 'phot_rp_mean_mag'
        
        query_select = f'SELECT TOP {num} source.{dist_col}, \
                        source.{ra_col}, source.{dec_col}, source.{dist84_col}, source.{dist16_col}, \
                        source.{gmag_col}, source.{bpmag_col}, source.{rpmag_col}, source.source_id'
        
        if var == True:
            query = f"{query_select} \
            FROM gaiadr3.vari_summary AS var \
            JOIN gaiadr3.gaia_source AS source ON var.source_id=source.source_id \
            WHERE source.has_mcmc_gspphot='true'"
            sf = 'Gaia_var.fits'
        
        elif var == False:
            query = f"{query_select} \
            FROM gaiadr3.gaia_source AS source \
            WHERE source.has_mcmc_gspphot='true'"
            sf = 'Gaia.fits'
            

    job = Gaia.launch_job_async(query, output_format='fits')
    print('1')
    results = job.get_results()

    print('1')
    
    c1 = SkyCoord(ra = results[ra_col],
              dec = results[dec_col],
              distance = results[dist_col],
              frame = 'icrs')
    
    if cartesian == True:
        xcoord, ycoord, zcoord = results[x_col], results[y_col], results[z_col]
    else:
        xcoord = c1.transform_to('galactocentric').x.to('pc') + 8122*u.pc
        ycoord = c1.transform_to('galactocentric').y.to('pc')
        zcoord = c1.transform_to('galactocentric').z.to('pc') - 20.8*u.pc
    
    stars = QTable([results['source_id'], results[ra_col], results[dec_col], results[dist_col], results[dist84_col], results[dist16_col], xcoord, ycoord, zcoord, results[gmag_col], results[bpmag_col], results[rpmag_col]],
                   names=('id', 'ra', 'dec', 'dist', 'dist84', 'dist16', 'x', 'y', 'z', 'g', 'bp', 'rp'))


    savefile = f'../{sf}'
    if save:
        if os.path.exists(savefile):
            os.remove(savefile)    
        stars.write(savefile, format='fits')

        print(f'{len(stars)} stars retrieved and saved to {savefile}')

    else:
        print(f'{len(stars)} stars retrieved')
    return c1, stars




def readFile(filename):
    filepath = f'../{filename}.fits'
    stars = Table.read(filepath, format='fits')
    c1 = SkyCoord(ra = stars['ra'],
              dec = stars['dec'],
              distance = stars['dist'],
              frame = 'icrs')

    return c1, stars
    



def onEllipsoid(event, t0,  c1, stars, tol):
    # event is a SkyCoord with RA, Dec, distance of event (i.e. SN 1987A)
    # t0 is the time event was observed on Earth
    # c1 is SkyCoord with RA, Dec, distance of stars
    # stars is astropy Table with necessary info 
    # tol is the tolerance for stars being on the ellipse
    # Returns table of stars currently within (-tol, tol) of being on the ellipse 
    
    t1 = Time.now()
    dt = t1-t0 # time since event was observed on Earth
    
    
    # Ellipsoid geometry
    c = event.distance.to('lyr') / 2 # dist to foci from ellipse center (half the distance from Earth to SN1987A, the two foci)   
    a = (((dt.to('s') * const.c) / 2) + c).to('lyr') # semi-major axis of ellipse
    # first term is the distance along the major axis beyond Earth -- it is half the distance light would travel in the time since the event was observed
     
    
    # Star geometry
    d1 = stars['dist'] # dist to stars
    d2 = c1.separation_3d(event) # dist from all GCNS stars to SN 1987A
    
    
    # Which stars are within some tolerance of being ON the ellipse?
    OYES = np.abs((d1.to('lyr').value + d2.to('lyr').value) - (2 * a.to('lyr').value)) <= tol
    # check if sum of focal point distances minus the major axis diameter is within the interval (-tol, tol)
    
    return c1[OYES], stars[OYES]


def crossEllipsoid(event, t0,  c1, stars, tol, start):
    # event is a SkyCoord with RA, Dec, distance of event (i.e. SN 1987A)
    # t0 is the time event was observed on Earth
    # c1 is SkyCoord with RA, Dec, distance of stars
    # stars is astropy Table with necessary info 
    # tol is the tolerance for stars crossing the ellipse
    # start is the start time from when we consider stars crossing the ellipse
    # Returns table of stars that have crossed the ellipse since start 
    
    
    t1 = Time.now()
    c = event.distance.to('lyr') / 2
    d1 = stars['dist'] # dist to stars
    d2 = c1.separation_3d(event) # dist from all GCNS stars to SN 1987A
    
    etime = d2.to('lyr') + d1.to('lyr') - (2*c)
    
    gstart = Time(str(start), format='decimalyear')
    gstart_t0 = (gstart-t0).to('year').value # years between start time and time the event was observed on Earth

    crossings = ((etime.value >= gstart_t0-tol) & # since start
      (etime.value < ((t1-t0).to('year').value+0.1)) # up to 0.1 years from now
     ) 

    
    return c1[crossings], stars[crossings]
     

def login(username, password):
    Gaia.login(user=username, password=password)

def logout():
    Gaia.logout()

def getLC(lc_table, source_id, band):
    # Returns light curve for a specific band and source id from a light curve
    # table of all sources in all bands
    source_mask = lc_table['source_id'] == source_id
    source_lc = lc_table[source_mask]
    band_mask = source_lc['band'] == band
    band_lc = source_lc[band_mask]

    return band_lc
    
    
def varClass(source_id):
    # Returns the Gaia variable classification for a given source id

    query = f"SELECT best_class_name \
            FROM gaiadr3.vari_classifier_result \
            WHERE gaiadr3.vari_classifier_result.source_id = '{source_id}'"

    job = Gaia.launch_job_async(query, output_format='fits')
    results = job.get_results()
    return results['best_class_name']


def varClasses(source_id_tup):
    # Returns the Gaia variable classifications for a tuple of source ids

    query = f"SELECT best_class_name, source_id \
            FROM gaiadr3.vari_classifier_result \
            WHERE gaiadr3.vari_classifier_result.source_id IN {source_id_tup}"

    job = Gaia.launch_job_async(query, output_format='fits')
    results = job.get_results()
    return results

def xTime(star, c0=None, t0=None):
    # Returns the ellipsoid crossing time of the SkyCoord object(s)
    # if c0 and t0 are None, the ellipsoid defaults to SN 1987A

    if not c0 or not t0:
        # Properties of SN1987A
        t0 = Time({'year': 1987, 'month': 2, 'day': 23}, format='ymdhms')

        c0_radec = SkyCoord.from_name('SN 1987A')

        # Panagia (1999) https://ui.adsabs.harvard.edu/abs/1999IAUS..190..549P/abstract
        d0 = 51.4 * u.kpc
        d0_err = 1.2 * u.kpc

        c0 = SkyCoord(ra=c0_radec.ra, dec=c0_radec.dec, distance=d0)
    
    
    c = c0.distance.to('lyr') / 2
    d1 = star.distance # dist to stars
    d2 = star.separation_3d(c0) # dist from all GCNS stars to SN 1987A
    
    etime = d2.to('lyr') + d1.to('lyr') - (2*c)
    xtime = etime.value*u.year + t0
    return xtime.jd


def plotLC(sid, star, glcDict, bplcDict, rplcDict, y='flux'):
    # Plots the light curves for a star in the G, BP, and RP bands
    # Needs the source id of the star, the SkyCoord object corresponding to the star
    # and three dictionaries containing the source ids of stars as keys and the
    # light curve tables as items

    xtime = xTime(star)[0]

    glcTimes = Time(glcDict[sid]['time'].value + 2455197.5, format='jd')
    blcTimes = Time(bplcDict[sid]['time'].value + 2455197.5, format='jd')
    rlcTimes = Time(rplcDict[sid]['time'].value + 2455197.5, format='jd')
    
    if y != 'flux':
        glcY = glcDict[sid]['mag']
        blcY = bplcDict[sid]['mag']
        rlcY = rplcDict[sid]['mag']
        gerr = None
        berr = None
        rerr = None

    else:
        glcY = glcDict[sid]['flux']
        blcY = bplcDict[sid]['flux']
        rlcY = rplcDict[sid]['flux']
        gerr = glcDict[sid]['flux_error']
        berr = bplcDict[sid]['flux_error']
        rerr = rplcDict[sid]['flux_error']

    fig, ax = plt.subplots(3, sharex=True, figsize=[10,6], dpi=100)

    ax[0].errorbar(glcTimes.value, glcY, yerr=gerr, fmt='o', c='green')
    ax[1].errorbar(blcTimes.value, blcY, yerr=berr, fmt='o', c='blue')
    ax[2].errorbar(rlcTimes.value, rlcY, yerr=rerr, fmt='o', c='red')


    ax[0].vlines(xtime, ymin=min(glcY.value), ymax=max(glcY.value), color='green')
    ax[1].vlines(xtime, ymin=min(blcY.value), ymax=max(blcY.value), color='blue')
    ax[2].vlines(xtime, ymin=min(rlcY.value), ymax=max(rlcY.value), color='red')

    ax[2].set_xlabel('BJD')

    if y != 'flux':
        ax[1].set_ylabel('Mag')
    else:
        ax[1].set_ylabel('Flux (electrons/s)')
    ax[0].set_title(f'Source {sid}')
    





    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Select targets on SETI Ellipsoid'
        )
    parser.add_argument(
        '--v', type = int, default=1,
        help='Only variable stars (1) or all stars (0)'
        )
    parser.add_argument(
        '--ns', type = int, default=1,
        help='Use Gaia Catalogue of Nearby Stars (GCNS) (1) or all star (0)'
        )
    parser.add_argument(
        '--start', type=float, default=2014.569312182902,
        help='Stars that have crossed the SETI ellipsoid since when?'
        )
    parser.add_argument(
        '--tol', type=float, default=0.1,
        help='How much tolerance for being on ellipse? (ly)'
        )
    parser.add_argument(
        '--num', type=int, default=100000,
        help='Max number of targets'
        )
    parser.add_argument(
        '--cross', type=int, default=1,
        help='(1) which stars have crossed ellipsoid since start? (0) which stars are on ellipsoid now?'
        )
    parser.add_argument(
        '--u', type=str, default=None,
        help='Gaia login username'
    )
    parser.add_argument(
        '--p', type=str, default=None,
        help='Gaia login password'
    )
    parser.add_argument(
        '--save', type=int, default=1,
        help='Save to a table (1)?'
    )
  

    args = parser.parse_args()

    if args.v == 1:
        v = True
    else:
        v = False
    
    if args.ns == 1:
        ns = True
    else:
        ns = False
    
    if args.cross == 1:
        cross = True
    else:
        cross = False
    
    if args.save == 1:
        save = True
    else:
        save = False
    
    
    
    start = args.start
    tol = args.tol
    num = args.num
    username = args.u
    password = args.p

    if username and password:
        login(username, password)

    
    c1, stars = queryGaia(v, ns, num, save)