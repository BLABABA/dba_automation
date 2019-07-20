""" 
    utility.py provide all functions:

    - loadUnitCell(path)
    path is the dataPath, dataPath needs to be defined
    in the files.py
    
"""

import os
import sys
import numpy as np
from copy import deepcopy
from pymatgen import Molecule
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.io.xyz import XYZ
from itertools import filterfalse
from shutil import copy2
import math

def getSingleMol(supercell, middleSite, bondDict, middleSiteIndex):
    candidates = [middleSite]
    candidatesIndex = [middleSiteIndex]
    tmpSites = []
    singleMol = dict()
    while candidates != []:
        for site in candidates:
            bondCutoffMax = 0
            for pair in bondDict.keys():
                if (bondDict[pair] >= bondCutoffMax) and (str(site.specie) in pair):
                    bondCutoffMax = bondDict[pair]
            allNeighbors = supercell.get_neighbors(site, bondCutoffMax, include_index=True)
            for neighbor in allNeighbors:
                sitePair = (str(site.specie), str(neighbor[0].specie))
                if neighbor[1] <= bondDict[sitePair]:
                    tmpSites += [neighbor]
        # ugly solution
        tmpSiteslist = list()
        for tmpsite in tmpSites:
            if tmpsite not in tmpSiteslist:
                tmpSiteslist += [tmpsite]
        tmpSites = deepcopy(tmpSiteslist)
        for i, site in enumerate(candidates):
            singleMol[candidatesIndex[i]] = site
        candidates = []
        candidatesIndex = []
        for site in tmpSites:
            # check if the site index is in the single molecule index
            if site[2] not in singleMol.keys():
                candidates += [site[0]]
                candidatesIndex += [site[2]]
        print('Number of atoms found in this molecule:', len(singleMol))
        tmpSites = []
    return singleMol

def getCentralSingleMol(supercell, bondDict, middle=[0.5, 0.5, 0.5]):
    # check if the frac_coord is smaller than zero
    # if smaller than zero, change the middle site coords to negative
    if min(supercell.frac_coords[:, 0]) < 0:
        for i, val in enumerate(middle):
            middle[i] = val * (-1)
    # find site in the middle
    dist = 1
    for i, site in enumerate(supercell.sites):
        if np.linalg.norm(middle-site.frac_coords) < dist:
            dist = np.linalg.norm(middle-site.frac_coords)
            middleSite = site
            middleSiteIndex = i
    print('The site closest to the middle is', middleSite)
    print('The corresponding site index is', middleSiteIndex)
    # pick up all the atom pairs within bond van der waals distance
    # centralSingleMol is the list of sites which belong to the central molecule
    centralSingleMol = getSingleMol(supercell, middleSite, bondDict, middleSiteIndex)
    return centralSingleMol

def getBondDict(supercell, bondCutoff):
    bondDict = dict()
    speciesList = list(set(supercell.species))
    for i in range(len(speciesList)):
        speciesList[i] = str(speciesList[i])
    for a in speciesList:
        for b in speciesList:
            if (a, b) in bondCutoff.keys():
                bondDict[(a, b)] = bondCutoff[(a, b)]
    duplicate = dict()
    for pairs in bondDict.keys():
        (a, b) = pairs
        if (b, a) not in bondDict:
            duplicate[(b, a)] = bondDict[pairs]
    bondDict.update(duplicate)
    return bondDict

def getSuperCell(unitcell, finegrid):
    if finegrid != []:
        print('Reminder: Please make sure you type in the correct fine grid.')
        unitcell.make_supercell(finegrid)
    else:
        sys.exit('No definitions found in finegrid, please make sure you input it when define automator.\n')
    return unitcell

# !!! important !!!
# this function sets the charge percentage threshold as 1%
def getHolePositions(chargeMatrix, singleMol, unitcell, bondDict, chargeThreshold=0.01):
    bondlength = 0
    for key in bondDict:
        if bondDict[key] >= bondlength:
            bondlength = bondDict[key]
    chargeIndex = np.where(chargeMatrix[:, 4] > chargeThreshold)[0]
    holePositions = dict()
    for charindex in chargeIndex:
        chargeSite = singleMol.sites[charindex]
        neighborSites = singleMol.get_neighbors(chargeSite, bondlength)
        twoNeighbors = []
        # delete the neighbors which are H
        neighborSites[:] = filterfalse(lambda x: str(x[0].specie) == 'H', neighborSites)
        # control the length of the twoNeighbors list smaller or equal than 2
        for neighbor in neighborSites:
            if len(twoNeighbors) < 2:
                twoNeighbors += [neighbor]
            else:
                twoNeighbors += [neighbor]
                tmpBondLength = 0
                for site in twoNeighbors:
                    if site[1] > tmpBondLength:
                        tmpBondLength = site[1]
                        removeSite = site
                twoNeighbors.remove(removeSite)
        holePositions[charindex] = findHole(unitcell, twoNeighbors, chargeSite)
    return holePositions

def findHole(unitcell, twoNeighbors, chargeSite):
    point1 = deepcopy(twoNeighbors[0][0].coords)
    point2 = deepcopy(twoNeighbors[1][0].coords)
    point3 = deepcopy(chargeSite.coords)
    normalVec = calNormalVector(point1, point2, point3)
    shift = -0.8
    holePosition = [0, 0, 0]
    for i in range(3):
        holePosition[i] = chargeSite.coords[i] + normalVec[i]*shift
    tmpcell = unitcell.copy()
    tmpcell.append('He', holePosition, coords_are_cartesian=True)
    return tmpcell.sites[-1].frac_coords

def calNormalVector(p1, p2, p3):
    # generate the vector
    vector = [0, 0, 0]
    vector[0] = (p2[1]-p1[1])*(p3[2]-p1[2]) - (p2[2]-p1[2])*(p3[1]-p1[1])
    vector[1] = (p2[2]-p1[2])*(p3[0]-p1[0]) - (p2[0]-p1[0])*(p3[2]-p1[2])
    vector[2] = (p2[0]-p1[0])*(p3[1]-p1[1]) - (p2[1]-p1[1])*(p3[0]-p1[0])
    # normalize it
    sigma = vector[0]**2 + vector[1]**2 + vector[2]**2
    sigma = math.sqrt(sigma)
    for i in range(3):
        vector[i] = vector[i] / sigma
    return vector

def getMoleculeIndex(singleMol, cubecell, threshold = 0.01):
    molIndex = dict()
    for i, molsite in enumerate(singleMol.sites):
        for j, cellsite in enumerate(cubecell.sites):
            if (np.linalg.norm(molsite.coords-cellsite.coords)<threshold) and (str(cellsite.specie)==str(molsite.specie)):
                molIndex[i] = j
            continue
    if len(molIndex.keys()) != singleMol.num_sites:
        print('Error!!!')
        print('The number of atoms within a single molecule found in the cube file\
            is not the same as the one stored under /data/singlemolecule')
        print('Please make sure there is no change of the output single \
            molecule from step 1')
        return 0
    else:
        return molIndex

def getMolShare(chargeMatrix, molIndex):
    molshare = 0
    for key in molIndex.keys():
        molshare += chargeMatrix[molIndex[key]][4]
    return molshare
    
def getXctPath(path, checklist):
    filelist = os.listdir(path)
    if "ACF.dat" not in filelist:
        for name in filelist:
            if os.path.isdir(os.path.join(path, name)):
                checklist = getXctPath(os.path.join(path, name), checklist)
    else:
        if not any(name.endswith("cube") for name in filelist):
            print()
            print("Warning!!!")
            print('In folder', path, 'we found ACF.dat but no .cube file.')
            print('Please check if you put all necessary output there.')
        else:
            checklist += [path]
    return checklist

def getPrimitiveCell(supercell):
    pmganalyzer = SpacegroupAnalyzer(supercell)
    primitive = pmganalyzer.find_primitive()
    return primitive

# getAllMols returns a list of pmg Molecule objs, including all fragments inside the supercell
def getAllMols(supercell, bondDict):
    # molList is the list of pymatgen Molecule object
    # tmpMol is pyatgen Molecule object
    molList = []
    while len(supercell.sites) != 0:
        # function getCentralSingleMol returns a dictionary
        # the keys are the index of each sites in supercell
        print('length of supercell:', len(supercell.sites))
        molsites = Molecule([], [])
        molindex = list()
        tmpMol = getCentralSingleMol(supercell, bondDict)
        for siteIndex in tmpMol.keys():
            molsites.append(str(tmpMol[siteIndex].specie), tmpMol[siteIndex].coords)
            molindex.append(siteIndex)
        supercell.remove_sites(molindex)
        molList += [molsites]
    return molList

# take a list of Molecule objects and return the smallest intermolecular distances
def getInterMolLen(molslist):
    mollen = 0
    for mol in molslist:
        if len(mol.sites) > mollen:
            mollen = len(mol.sites)
    for mol in molslist[:]:
        if len(mol.sites) < mollen:
            molslist.remove(mol)
    if len(molslist) >= 2:
        # choose two random molecules and get an initial intermolecular distance
        interLen = np.linalg.norm(molslist[0].center_of_mass - molslist[1].center_of_mass)
        for i, mola in enumerate(molslist):
            for j, molb in enumerate(molslist):
                # make sure not counting the difference between the same molecules
                if (i != j) and (np.linalg.norm(mola.center_of_mass-molb.center_of_mass) < interLen):
                    interLen = np.linalg.norm(mola.center_of_mass-molb.center_of_mass)
        return interLen
    else:
        raise Exception('Error!!! There are less than two complete molecules inside constructed supercell.\n')

# take a pmg structure and convergence length
# return the atom index in three dimensions
def getAtomIndex(struct, convrange):
    dirabc = list()
    for d in range(3):
        cutoff = convrange / struct.lattice.abc[d]
        dirtmp = np.where(np.logical_or(struct.frac_coords[:, d] < cutoff, struct.frac_coords[:, d] > (1-cutoff)))[0]
        dirabc += [dirtmp]
    return dirabc[0], dirabc[1], dirabc[2]

# take the indices and chargematrix, return
# the charge share for indicated indices
def getChargeShare(indices, chargematrix):
    return np.sum(chargematrix[indices], axis=0)[4]

def checkDataFolder(path):
    folderlist = ['dba', 'singlemolecule', 'supercell', 'unitcell']
    for foldername in folderlist:
        try:
            os.mkdir(os.path.join(path, foldername))
            print('Directory', foldername, 'created.')
        except FileExistsError:
            print('Directory', foldername, 'already exists.')

def copyInput(file, path):
    unitcellpath = os.path.join(path, 'unitcell')
    print('Copy unitcell file to', unitcellpath, '.')
    copy2(file, unitcellpath)

def getMPC(supercell, finegrid, molslist):
    # get the number of unitcells used to build the supercell
    # get the number of atoms per cell
    supercellsize = finegrid[0] * finegrid[1] * finegrid[2]
    atomPerCell = len(supercell.sites) / supercellsize
    if len(molslist) == 0:
        sys.exit('There is no complete molecules founded in molslist...')
    else:
        tmpmol = molslist[0].copy()
    mpc = atomPerCell / len(tmpmol.sites)
    # check if mpc is an integer
    if mpc.is_integer():
        print('The number of molecules per cell is:', int(mpc))
    else:
        print('The number of molecules per cell is not an integer, exiting program...')
    return int(mpc)

def getEdgeFragmentsIndexNew(supercell, mollen, intermoldist, finegrid, bondDict, adjustment=1.0):
    print('Looking for the edge fragments index, might take up to an hour...')
    indexlist = list()
    celllist = list()
    # decide if cutoff need a different sign
    if max(supercell.frac_coords[:, 0]) < 0:
        sign = -1
    else:
        sign = 1
    # check in three ranges
    for i in range(3):
        # so use backup supercell everytime
        tmpcell = supercell.copy()
        cutoff = intermoldist * adjustment * sign / tmpcell.lattice.abc[i]
        print('The cutoff is:', cutoff)
        # chop off the middle of the supercell, up until cutoff + mol length
        chopcutoff = (intermoldist * adjustment + mollen) * sign / tmpcell.lattice.abc[i]
        print('The chopcutoff is:', chopcutoff)
        # make sure this chopcutoff does not pass the middle
        # if the chopcutoff pass the middle, then do not chop the middle off
        if abs(chopcutoff) < 0.5:
            if sign < 0:
                chopindex = np.where(np.logical_and(tmpcell.frac_coords[:, i] < chopcutoff, tmpcell.frac_coords[:, i] > (-1-chopcutoff)))[0]
            else:
                chopindex = np.where(np.logical_and(tmpcell.frac_coords[:, i] > chopcutoff, tmpcell.frac_coords[:, i] < (1-chopcutoff)))[0]
            tmpcell.remove_sites[chopindex]
        # decreaselist tells the index for atoms within the cutoff range
        # search start from these atoms
        if sign < 0:
            decreaselist = np.where(np.logical_or(tmpcell.frac_coords[:, i] > cutoff, tmpcell.frac_coords[:, i] < (-1-cutoff)))[0]
        else:
            decreaselist = np.where(np.logical_or(tmpcell.frac_coords[:, i] < cutoff, tmpcell.frac_coords[:, i] > (1-cutoff)))[0]
        print('The length of decreaselist is:', len(decreaselist))
        # edgelist is a list of sites, it contains the sites belong to the edge fragments, not index
        # find out the index later
        edgesite = list()
        # key function is: getSingleMol(supercell, middleSite, bondDict, middleSiteIndex)
        for cutoffindex in decreaselist:
            # if this index in the decreaselist is already in the cutoffindex
            # then don't waste time to find out the fragment for it
            if tmpcell.sites[cutoffindex] in edgesite:
                pass
            else:
                # choose the first site index in the decreaselist as the starting middleSiteIndex
                # getSingleMol returns a dictionary, key is index, value is site
                fragment = getSingleMol(tmpcell, tmpcell.sites[cutoffindex], bondDict, cutoffindex)
                for siteindex in fragment.keys():
                    edgesite.append(fragment[siteindex])
            print('The length of edgeindexlist is:', len(edgesite))
        # now the fragmentlist is the list full of edge fragment sites
        edgeindex = list()
        for i, site in enumerate(supercell.sites):
            if site in edgesite:
                edgeindex.append(i)
        # before remove the edge sites, make a copy
        print('The length of edge index is:' len(edgeindex))
        tmpcell = supercell.copy()
        tmpcell.remove_sites(edgeindex)
        indexlist.append(edgeindex)
        celllist.append(tmpcell)
    return indexlist[0], indexlist[1], indexlist[2], celllist[0], celllist[1], celllist[2]

# def getEdgeFragmentsIndex(supercell, mollen, intermoldist, finegrid, bondDict, adjustment=1.0):
#     print('Looking for the edge fragments index, might take up to an hour...')
#     indexlist = list()
#     celllist = list()
#     # check in three ranges
#     for i in range(3):
#         # testing, fix i as the third dimension
#         # i = 2
#         # because every time need to delete some sites
#         # so use backup supercell everytime
#         tmpcell = supercell.copy()
#         # fragmentlist is a list of sites, it contains the sites belong to the edge fragments, not index
#         # find out the index later
#         fragmentlist = list()
#         # check the range of the supercell fractional coordinates
#         # if it's from -1 to 0, need to change the cutoff range too
#         if max(supercell.frac_coords[:, 0]) < 0:
#             adjustment = adjustment * (-1)
#         cutoff = intermoldist * adjustment / tmpcell.lattice.abc[i]
#         print('The cutoff is:', cutoff)
#         # decreaselist tells the index for atoms within the cutoff range
#         # search start from these atoms
#         if max(supercell.frac_coords[:, 0]) < 0:
#             decreaselist = np.where(np.logical_or(tmpcell.frac_coords[:, i] > cutoff, tmpcell.frac_coords[:, i] < (-1+cutoff)))[0]
#         else:
#             decreaselist = np.where(np.logical_or(tmpcell.frac_coords[:, i] < cutoff, tmpcell.frac_coords[:, i] > (1-cutoff)))[0]
#         # delete some sites in the middle to make this process easier
#         # delete the sites from tmpcell that are part of the edge fragments
#         # the key function is: getCentralSingleMol(supercell, bondDict)
#         # or the key function is: getSingleMol(supercell, middleSite, bondDict, middleSiteIndex)
#         while decreaselist.size != 0:
#             print('length of residual edge sites:', len(decreaselist))
#             print('The length of supercell:', len(tmpcell.sites))
#             # choose the first site index in the decreaselist as the starting middleSiteIndex
#             # getSingleMol returns a dictionary, key is index, value is site
#             fragment = getSingleMol(tmpcell, tmpcell.sites[decreaselist[0]], bondDict, decreaselist[0])
#             fragmentindex = list()
#             for siteindex in fragment.keys():
#                 fragmentlist.append(fragment[siteindex])
#                 fragmentindex.append(siteindex)
#             # to delete the repeated sites
#             fragmentlist = list(set(fragmentlist))
#             tmpcell.remove_sites(fragmentindex)
#             # now some of the sites are removed from tmpcell, need to recaluclate the decrease list
#             # this list should be continuously decrasing
#             if max(supercell.frac_coords[:, 0]) < 0:
#                 decreaselist = np.where(np.logical_or(tmpcell.frac_coords[:, i] > cutoff, tmpcell.frac_coords[:, i] < (-1+cutoff)))[0]
#             else:
#                 decreaselist = np.where(np.logical_or(tmpcell.frac_coords[:, i] < cutoff, tmpcell.frac_coords[:, i] > (1-cutoff)))[0]
#             # delete the site index in decreaselist if it already exists in the fragmentlist
#             # dellist = list()
#             # for i, siteindex in enumerate(decreaselist):
#             #     if tmpcell.sites[siteindex] in fragmentlist:
#             #         dellist.append(i)
#             # decreaselist = np.delete(decreaselist, dellist)
#         # now the fragmentlist is the list full of edge fragment sites
#         print('for testing purpose...')
#         print('length of fragmentlist:', len(fragmentlist))
#         print('length of tmpcell:', len(tmpcell.sites))
#         cellfragmentindex = np.array([])
#         celllist.append(tmpcell)
#         print('Searching for edge fragment site index...')
#         for site in fragmentlist:
#             cellfragmentindex = np.append(cellfragmentindex, np.where(supercell.frac_coords == site.frac_coords)[0])
#         cellfragmentindex = cellfragmentindex.astype(int).tolist()
#         indexlist.append(cellfragmentindex)
#     return indexlist[0], indexlist[1], indexlist[2], celllist[0], celllist[1], celllist[2]

def getMoleculeLength(molslist):
    # make sure this list is not empty
    if len(molslist) == 0:
        raise Exception('The number of molecules in molslist is zero, \
            please check make sure your structure is correct')
    else:
        tmpmol = molslist[0].copy()
    # get the longest distance within one molecule
    dist = 0
    for i, sitex in enumerate(tmpmol.sites):
        for j, sitey in enumerate(tmpmol.sites):
            if i < j:
                tmpdist = np.linalg.norm(sitex.coords-sitey.coords)
                if tmpdist > dist:
                    dist = tmpdist
    # thus give the longest distance within one molecule
    return dist

# def getEdgeFragmentsIndexDel(supercell, mollen, intermoldist, finegrid, bondDict, adjustment=1.0):
#     print('Looking for the edge fragments index, might take up to an hour...')
#     indexlist = list()
#     celllist = list()
#     # make a dictionary to preserve the original index
#     print('Building site-index dictionary...')
#     celldict = dict()
#     for i, site in enumerate(supercell.sites):
#         celldict[site] = i
#     # make sure check the supercell fractional sign
#     # if it's necessary to adjust the sign
#     if max(supercell.frac_coords[:, 0]) < 0:
#         sign = -1
#     else:
#         sign = 1
#     # check in three ranges
#     for i in range(3):
#         # so use backup supercell everytime
#         tmpcell = supercell.copy()
#         # fragmentlist is a list of sites, it contains the sites belong to the edge fragments, not index
#         # find out the index later
#         edgeindexlist = list()
#         # check the range of the supercell fractional coordinates
#         # if it's from -1 to 0, need to change the cutoff range too
#         adjustment = adjustment * sign
#         cutoff = intermoldist * adjustment / tmpcell.lattice.abc[i]
#         print('The cutoff is:', cutoff)
#         # chop off the middle of the supercell, up until cutoff + mol length
#         chopcutoff = (intermoldist * adjustment + mollen) * sign / tmpcell.lattice.abc[i]
#         # make sure this chopcutoff does not pass the middle
#         # if the chopcutoff pass the middle, then do not chop the middle off
#         if abs(chopcutoff) < 0.5:
#             if sign < 0:
#                 chopindex = np.where(np.logical_and(tmpcell.frac_coords[:, i] < chopcutoff, tmpcell.frac_coords[:, i] > (-1-chopcutoff)))[0]
#             else:
#                 chopindex = np.where(np.logical_and(tmpcell.frac_coords[:, i] > chopcutoff, tmpcell.frac_coords[:, i] < (1-chopcutoff)))[0]
#             tmpcell.remove_sites[chopindex]
#         # decreaselist tells the index for atoms within the cutoff range
#         if sign < 0:
#             decreaselist = np.where(np.logical_or(tmpcell.frac_coords[:, i] > cutoff, tmpcell.frac_coords[:, i] < (-1-cutoff)))[0]
#         else:
#             decreaselist = np.where(np.logical_or(tmpcell.frac_coords[:, i] < cutoff, tmpcell.frac_coords[:, i] > (1-cutoff)))[0]
#         print('The length of decreaselist is:', len(decreaselist))
#         # select fragments from based on the decreaselist
#         for cutoffindex in decreaselist:
#             # if this index in the decreaselist is already in the cutoffindex
#             # then don't waste time to find out the fragment for it
#             # should extract the correct index from celldict
#             if celldict[tmpcell.sites[cutoffindex]] in edgeindexlist:
#                 pass
#             else:
#                 # choose the first site index in the decreaselist as the starting middleSiteIndex
#                 # getSingleMol returns a dictionary, key is index, value is site
#                 fragment = getSingleMol(tmpcell, tmpcell.sites[cutoffindex], bondDict, cutoffindex)
#                 for siteindex in fragment.keys():
#                     edgeindexlist.append(int(celldict[tmpcell.sites[siteindex]]))
#             print('The length of edgeindexlist is:', len(edgeindexlist))
#         # now the fragmentlist is the list full of edge fragment sites
#         tmpcell.remove_sites(edgeindexlist)
#         indexlist.append(edgeindexlist)
#         celllist.append(tmpcell)
#     return indexlist[0], indexlist[1], indexlist[2], celllist[0], celllist[1], celllist[2]

def getEdgeFragmentsIndexNosearch(supercell, mollen, intermoldist, finegrid, bondDict, adjustment=1.0):
    print('Looking for the edge fragments index, might take up to an hour...')
    indexlist = list()
    celllist = list()
    # decide if cutoff need a different sign
    if max(supercell.frac_coords[:, 0]) < 0:
        sign = -1
    else:
        sign = 1
    # check in three ranges
    for i in range(3):
        # so use backup supercell everytime
        tmpcell = supercell.copy()
        # fragmentlist is a list of sites, it contains the sites belong to the edge fragments, not index
        # find out the index later
        edgeindexlist = list()
        cutoff = intermoldist * adjustment * sign / tmpcell.lattice.abc[i]
        print('The cutoff is:', cutoff)
        # decreaselist tells the index for atoms within the cutoff range
        # search start from these atoms
        if sign < 0:
            decreaselist = np.where(np.logical_or(tmpcell.frac_coords[:, i] > cutoff, tmpcell.frac_coords[:, i] < (-1-cutoff)))[0]
        else:
            decreaselist = np.where(np.logical_or(tmpcell.frac_coords[:, i] < cutoff, tmpcell.frac_coords[:, i] > (1-cutoff)))[0]
        print('The length of decreaselist is:', len(decreaselist))
        for cutoffindex in decreaselist:
            # if this index in the decreaselist is already in the cutoffindex
            # then don't waste time to find out the fragment for it
            if cutoffindex in edgeindexlist:
                pass
            else:
                # choose the first site index in the decreaselist as the starting middleSiteIndex
                # getSingleMol returns a dictionary, key is index, value is site
                fragment = getSingleMol(tmpcell, tmpcell.sites[cutoffindex], bondDict, cutoffindex)
                for siteindex in fragment.keys():
                    edgeindexlist.append(int(siteindex))
            print('The length of edgeindexlist is:', len(edgeindexlist))
        # now the fragmentlist is the list full of edge fragment sites
        tmpcell.remove_sites(edgeindexlist)
        indexlist.append(edgeindexlist)
        celllist.append(tmpcell)
    return indexlist[0], indexlist[1], indexlist[2], celllist[0], celllist[1], celllist[2]