import pandas as pd, numpy as np
import sys, time, random, string, os
from synthicity.utils import misc
from urbandeveloper import elasticity_model_2SLS
from sqlalchemy import *

#import dataset
np.random.seed(1)
SHIFTAMOUNT = 1.0 # if demand exceeds supply
RESUNITSIZE = 1500 # should probably vary, but is currently set to 1000
BSQFT_JOB = 400
# MAXLOTSIZE = 500000 # 5 acres-ish - limit size of largest development ## I changed the 2 to a 5, so max acres is now ~12.5
# MINLOTSIZE = 100
#BUILDINGTYPEORDER = [12,3,2,1,14,4,10,11,7,8,9]
#BUILDINGTYPEORDER = [3,2,24,20,11,5,17,18,9,22] #DRCOG, including mixed use
#BUILDINGTYPEORDER = [3,2,24,20,5,17,18,9,22]
BUILDINGTYPEORDER = [5,17,18,9,22,3,2,24,20]
number_of_zones = 2804

inv_type_d = { 
  #'2,3,20,24,11': 'Residential',
  '2,3,20,24': 'Residential',
  '9,22': 'Industrial',
  '17,18': 'Retail',
  '5': 'Office'
}
for k,v in inv_type_d.items():
  for btyp in string.split(k,','): inv_type_d[int(btyp)]=v
  del inv_type_d[k]

# TODO get the real demand here
def get_simulated_demand(btyp,zone_id,hh_zone_diff,emp_zone_diff,zone_args):  ###Expressed in terms of sqft
  #return np.random.rand()*20000 # 2000 sqft in every zone!
  if (btyp in [2,3,20,24]) and (zone_id in hh_zone_diff.index):
      hh_diff = hh_zone_diff.loc[zone_id]
      if zone_args is not None:
          subsidized_demand = zone_args.subsidized_hh_demand[zone_id]
          hh_diff = hh_diff + subsidized_demand
      if hh_diff.values > 0:
          # print 'hh_diff'
          # print hh_diff
          #return hh_diff*RESUNITSIZE
          return hh_diff*300
  elif (btyp in [5,17,18,9,22]) and (zone_id in emp_zone_diff.index):
      emp_diff = emp_zone_diff.loc[zone_id]

      if zone_args is not None:
          subsidized_demand = zone_args.subsidized_emp_demand[zone_id]
          emp_diff = emp_diff
                     #+ subsidized_demand
      if emp_diff.values > 0:
          # print 'emp_diff'
          # print emp_diff
          #return emp_diff*BSQFT_JOB
          return emp_diff*50
  else:
      #return 1000
      #print 'No %s demand in zone %s.' % (btyp,zone_id)
      pass


price_shifters = {}
def shift_up(btyp,zone_id,elasticity, pct_sqft_chng):
    key = (btyp,zone_id)

    if np.isinf(pct_sqft_chng):

        shift_amt = 1.02384
    else:
        shift_amt = (elasticity * pct_sqft_chng)+1

    #condition: if the shift amount is greater than 100%, shift by the average amount which is 1.0238 (calculated from prior model runs)
    if shift_amt < 1.125:
    #price_shifters[key] = price_shifters.get(key,1.0)*shift_amt  ****incorrectly shifts prices up
        price_shifters[key] = shift_amt
    else:
    #price_shifters[key] = price_shifters.get(key,1.0)*1.02384    ****incorrectly shifts prices up
        shift_amt = 1.125
def run(dset,hh_zone_diff,emp_zone_diff,parcel_predictions,year=2010,min_building_sqft=400,min_lot_sqft=250,max_lot_sqft=500000,zone_args=None):

  np.random.seed(1)
  MINBUILDINGSQFT = min_building_sqft
  MAXLOTSIZE = max_lot_sqft
  MINLOTSIZE = min_lot_sqft
  #print os.getcwd()

#parcel_predictions = pd.read_csv(os.path.join(misc.data_dir(),'parcel_predictions.csv'),index_col='parcel_id') # feasible buildings
  parcels=dset.parcels
  #engine = create_engine('postgresql://postgres:postgres@localhost:5432/postgres', echo=False)

    ###add zone_county_relation table for debugging#


  #additions for implementing elasticity models
  #construct elasticity model class
  #e_model = elasticity_model.elasticity_model(dset)

  #////Uncomment emodel when done with testing
  '''e_model = elasticity_model_2SLS.elasticity_model(dset)
  elasticity_res = e_model.estimate_elasticity(e_model.zones)
  elasticity_non_res = e_model.estimate_non_res_elasticity(e_model.zones)
  '''
  elasticity_res = 1
  elasticity_non_res = 1


  #need to separate residential from non-residential buildings
  res_building_types = [2,3,20,24]
  elasticity_table = pd.DataFrame(columns=['residential_elasticity','non-residential_elasticity'])
  elasticity_table.index.name = 'year'
  elasticity_table.loc[year]=[elasticity_res, elasticity_non_res]
  #elasticity_table.to_sql('elasticities',engine, if_exists='append')


  if parcels.index.name !='parcel_id':
      parcels = parcels.set_index(parcels['parcel_id'])
  parcel_predictions['zone_id'] = parcels.zone_id.ix[parcel_predictions.index]



  newbuildings_d = {}
  for btyp in BUILDINGTYPEORDER:
    newbuildings = []

    #set elasticity based on building type
    if btyp in res_building_types:
        elasticity = elasticity_res

    else:
        elasticity = elasticity_non_res

    btyp_predictions = parcel_predictions[str(btyp)].dropna()
    #btyp_pro=parcel_predictions[btyp+ '_profit'].dropna()


    for zone_id in range(1,number_of_zones+1):
      if zone_args is not None:
        if zone_args.no_build[zone_id] == 1:
            continue

      # get the demands
      demand_sqft = get_simulated_demand(btyp,zone_id,hh_zone_diff,emp_zone_diff,zone_args)

        #gets total sqft in zone/building type combo
      #tot_sqft = (dset.zones.residential_sqft_zone.ix[zone_id]) + (dset.zones.non_residential_sqft_zone.ix[zone_id])

      try:
        pct_sqft_chng = 0 #pct_sqft_chng = (demand_sqft / tot_sqft)
      except:
          pct_sqft_chng = 0

      if pct_sqft_chng > 1:
        pct_sqft_chng = 1


      """
      if not demand_sqft:
          print "unutilized capacity " + str(btyp_predictions[parcel_predictions.zone_id == zone_id].sum())
          continue
    """
      # get the feasible buildings for this building type and zone_id
      choiceset = btyp_predictions[parcel_predictions.zone_id == zone_id]

      if len(choiceset.index) == 0:
        #if demand_sqft > 3000:
          # raise prices
        shift_up(btyp,zone_id,elasticity, pct_sqft_chng)  # add if statement above if this doesn't work
        continue
      #choiceset = choiceset*dset.parcels.ix[choiceset.index].shape_area*10.764 # convert to sqft
      choiceset = choiceset*parcels.ix[choiceset.index].parcel_sqft
      choiceset[choiceset<MINBUILDINGSQFT] = MINBUILDINGSQFT


      #print "capacity " +str(choiceset.sum()) +" versus demand " + str(demand_sqft) + " in zone " + str(zone_id)

      if demand_sqft is None:
          #print "unutilized capacity " + str(choiceset.sum()) + " in zone " + str(zone_id)
          continue
      #print "capacity " +str(choiceset.sum()) +" versus demand " + str(demand_sqft) + " in zone " + str(zone_id)
      # weight the choice by the FAR, which presumably is directly related to profitability
      # XG: this would be somewhat true if there were no constraint on the fars. But here, not true at all, because of constraints on fars.
      choiceset_ind = np.random.choice(choiceset.index,len(choiceset.index),replace=False,p=choiceset.values/choiceset.sum())
      """
      # pick the first X number of buildings in order to meet demand
      choiceset_sorted=np.sort(choiceset)
      choiset_sorted=choiceset_sorted[::-1]
      #buildthese = np.searchsorted(choiceset.ix[choiceset_ind].cumsum(),demand_sqft) # round up
      buildthese=np.searchsorted(choiceset_sorted.cumsum(), demand_sqft)
    """

      accu_built=0
      choice=np.zeros(len(choiceset_ind))
      i=0
      while (accu_built<demand_sqft.values):
          if (choiceset_ind.size>0):
            choice[i]=choiceset_ind[0]
            accu_built=accu_built+choiceset[choiceset_ind[0]]
            choiceset_ind=choiceset_ind[1:len(choiceset_ind)]
            i=i+1
          else:

            break
      choice=choice[choice>0]



      #if buildthese > choiceset_ind.size:
        # raise prices
        #lack=(demand_sqft-choiceset.ix[choiceset_ind].sum())/50
        #print "Capacity issue in zone " + str(zone_id)  +" of " + str(lack)
        #hift_up(btyp,zone_id)  ##Needs to be implemented, but this can be a later stage thing.  H
      #newbuildings.append(choiceset.ix[choiceset_ind[:buildthese]])

      newbuildings.append(choiceset.ix[choice])


      ## XG: in case of no new building
    try:
        newbuildings=pd.concat(newbuildings)
        parcel_predictions = parcel_predictions.drop(newbuildings.index)
        newbuildings_d[btyp] = newbuildings
        print "%d new buildings for btyp %d" % (len(newbuildings.index), btyp)
    except:
        print "%d new buildings for btyp %d" % (0, btyp)



  newbuildings = pd.DataFrame(newbuildings_d)
  newbuildings = newbuildings.stack().reset_index(level=1)
  newbuildings.columns = ["building_type_id","building_sqft"]
  """

  newbuildings['parcel_id']=newbuildings.index
  newbuildings['county_id']=parcel_predictions0.county_id[newbuildings.parcel_id]
  for var in list(newbuildings.columns.values):
    print newbuildings.groupby('county_id')[var].sum()
    """
  newbuildings['general_type'] = newbuildings['building_type_id'].map(inv_type_d)
  #newbuildings['lot_size'] = dset.parcels.ix[newbuildings.index].shape_area*10.764
  #newbuildings['lot_size'] = dset.parcels.ix[newbuildings.index].parcel_sqft
  newbuildings = pd.merge(newbuildings, dset.parcels, right_on='parcel_id', left_index=True)[['building_type_id', 'building_sqft', 'general_type', 'parcel_sqft']]
  newbuildings = newbuildings.rename(columns={"parcel_sqft": "lot_size"})
  newbuildings['residential_units'] = np.ceil((newbuildings.general_type=='Residential')*newbuildings.building_sqft/RESUNITSIZE)
  newbuildings = newbuildings[newbuildings.lot_size<MAXLOTSIZE]
  newbuildings = newbuildings[newbuildings.lot_size>MINLOTSIZE]

  ###reset for production
  #newbuildings['net_residential_units'] = newbuildings.residential_units.sub(
  #             dset.buildings.groupby('parcel_id').residential_units.sum().ix[newbuildings.index],fill_value=0)
  print newbuildings.describe()
  print newbuildings.groupby('building_type_id').building_sqft.sum()
  print newbuildings.groupby('building_type_id').residential_units.sum()
  #newbuildings.to_csv('new_buildings.csv')
  return newbuildings, price_shifters
  # XXX need to remove building that existed on these parcels 
  # before and add these buildings to the list of buildings

if __name__ == '__main__':  


  import dataset
  import cProfile

  dset = dataset.DRCOGDataset(os.path.join(misc.data_dir(),'drcog.h5'))


  #add variables for test sim
  emp_zone_diff = pd.read_csv('C:/Users/jmartinez/Documents/Projects/UrbanSim/Developer/emp_zone_diff.csv', index_col=0)
  hh_zone_diff = pd.read_csv('C:/Users/jmartinez/Documents/Projects/UrbanSim/Developer/hh_zone_diff.csv', index_col=0)
  parcel_predictions = pd.read_csv('C:/Users/jmartinez/Documents/Projects/UrbanSim/Developer/parcel_predictions.csv', index_col=0)
  zone_args = pd.read_csv('C:/Users/jmartinez/Documents/Projects/UrbanSim/Developer/zone_args.csv', index_col=0)
  min_building_sqft = 400
  min_lot_sqft = 500
  max_parcel_sqft = 200000

  fnc = "newbuildings, price_shifters  = run(dset,hh_zone_diff,emp_zone_diff,parcel_predictions,year=2011," +\
                             "min_building_sqft=min_building_sqft," +\
                             "min_lot_sqft=min_lot_sqft," +\
                             "max_lot_sqft=max_parcel_sqft,zone_args=zone_args)"
  cProfile.run(fnc, "c:/users/jmartinez/documents/profile")

  # newbuildings, price_shifters  = run(dset,hh_zone_diff,emp_zone_diff,parcel_predictions,year=2011,
  #                            min_building_sqft=min_building_sqft,
  #                            min_lot_sqft=min_lot_sqft,
  #                            max_lot_sqft=max_parcel_sqft,zone_args=zone_args)

  #newbuildings.to_csv('C:/Users/jmartinez/Documents/Projects/UrbanSim/Developer/new_buildings.csv')
  #price_shifters.to_csv('C:/Users/jmartinez/Documents/Projects/UrbanSim/Developer/price_shifters.csv')



