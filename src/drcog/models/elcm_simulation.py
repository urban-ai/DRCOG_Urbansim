import synthicity.urbansim.interaction as interaction
import pandas as pd, numpy as np, copy
from synthicity.utils import misc

def simulate(dset,year,depvar = 'building_id',alternatives=None,simulation_table = 'establishments',
              output_names=None,agents_groupby = ['income_3_tenure',],transition_config=None):

    output_csv, output_title, coeff_name, output_varname = output_names 

    if transition_config['Enabled']:
        ct = dset.fetch(transition_config['control_totals_table'])
        ct["total_number_of_jobs"] = (ct["total_number_of_jobs"]*transition_config['scaling_factor']).astype('int32')
        new_jobs = {"table": "dset.establishments","writetotmp": "establishments","model": "transitionmodel","first_year": 2010,"control_totals": "dset.%s"%transition_config['control_totals_table'],
                    "geography_field": "building_id","amount_field": "total_number_of_jobs","size_field":"employees"}
        import synthicity.urbansim.transitionmodel as transitionmodel
        transitionmodel.simulate(dset,new_jobs,year=year,show=True)
        
    dset.establishments.index.name = 'establishment_id'
    choosers = dset.fetch(simulation_table)
    placed_choosers = choosers[choosers[depvar]>0]

    movers = choosers[choosers[depvar]==-1]
    movers.loc[:, "zone_id"] = -1
    print "Total new agents and movers = %d" % len(movers.index)
    alternatives.building_sqft_per_job = alternatives.building_sqft_per_job.fillna(1000)
    alternatives.loc[:, 'spaces'] = alternatives.non_residential_sqft/alternatives.building_sqft_per_job  # corrected chained indexing error
    empty_units = alternatives.spaces.sub(placed_choosers.groupby('building_id').employees.sum(),fill_value=0).astype('int')
    empty_units = empty_units[empty_units>0].order(ascending=False)

    alts = alternatives.ix[empty_units.index]
    alts["supply"] = empty_units
    lotterychoices = True
    pdf = pd.DataFrame(index=alts.index)

    segments = movers.groupby(agents_groupby)

    for name, segment in segments:
        segment = segment.head(1)
        name = str(name)
        tmp_outcsv, tmp_outtitle, tmp_coeffname = output_csv%name, output_title%name, coeff_name%name
        ind_vars = dset.coeffs[(tmp_coeffname, 'fnames')][np.invert(dset.coeffs[(tmp_coeffname, 'fnames')].isnull().values)].values.tolist()
        SAMPLE_SIZE = alts.index.size 
        numchoosers = segment.shape[0]
        numalts = alts.shape[0]
        sample = np.tile(alts.index.values,numchoosers)
        alts_sample = alts #sample#alternatives
        alts_sample['join_index'] = np.repeat(segment.index.values,SAMPLE_SIZE)
        alts_sample = pd.merge(alts_sample,segment,left_on='join_index',right_index=True,suffixes=('','_r'))
        chosen = np.zeros((numchoosers,SAMPLE_SIZE))
        chosen[:,0] = 1
        sample, alternative_sample, est_params = sample, alts_sample, ('mnl',chosen)
        ##Interaction variables
        interaction_vars = [(var, var.split('_x_')) for var in ind_vars if '_x_' in var]
        for ivar in interaction_vars:
            if ivar[1][0].endswith('gt'):
                alternative_sample[ivar[0]] = ((alternative_sample[ivar[1][0]])>alternative_sample[ivar[1][1]]).astype('int32')
            if ivar[1][0].endswith('lt'):
                alternative_sample[ivar[0]] = ((alternative_sample[ivar[1][0]])<alternative_sample[ivar[1][1]]).astype('int32')
            else:
                alternative_sample[ivar[0]] = ((alternative_sample[ivar[1][0]])*alternative_sample[ivar[1][1]])
                
        est_data = pd.DataFrame(index=alternative_sample.index)
        for varname in ind_vars:
            est_data[varname] = alternative_sample[varname]
        est_data = est_data.fillna(0)
        data = est_data
        data = data.as_matrix()
        coeff = dset.load_coeff(tmp_coeffname)
        probs = interaction.mnl_simulate(data,coeff,numalts=SAMPLE_SIZE,returnprobs=1)
        pdf['segment%s'%name] = pd.Series(probs.flatten(),index=alts.index) 
            
    new_homes = pd.Series(np.ones(len(movers.index))*-1,index=movers.index)
    mask = np.zeros(len(alts.index),dtype='bool')

    for name, segment in segments:
        name = str(name)
        print "Assigning units to %d agents of segment %s" % (len(segment.index),name)
        p=pdf['segment%s'%name]
        def choose(p,mask,alternatives,segment,new_homes,minsize=None):

            choiceset = alternatives.loc[alternatives.supply >= minsize]

            p = copy.copy(p)
            #p[alternatives.supply<minsize] = 0
            p = p[alternatives.supply >= minsize]
            p_arr = p.values


            try:
            #indexes = np.random.choice(len(alternatives.index),len(segment.index),replace=False,p=p/p.sum())
              indexes = np.random.choice(choiceset.index, len(segment.index), replace=False, p=p_arr/p_arr.sum())
            except:
              print "WARNING: not enough options to fit agents, will result in unplaced agents"
              return mask,new_homes
            #new_homes.ix[segment.index] = alternatives.index.values[indexes]
            #alternatives["supply"].ix[alternatives.index.values[indexes]] -= minsize
            new_homes.ix[segment.index] = indexes
            #alternatives["supply"].ix[indexes] -= minsize
            alternatives.loc[indexes, "supply"] -= minsize

            return mask,new_homes
        tmp = segment['employees']
        for name, subsegment in reversed(list(segment.groupby(tmp.astype('int')))):
            mask,new_homes = choose(p,mask,alts,subsegment,new_homes,minsize=int(name))

    build_cnts = new_homes.value_counts()  #num estabs place in each building
    print "Assigned %d agents to %d locations with %d unplaced" % (new_homes.size,build_cnts.size,build_cnts.get(-1,0))
    new_homes_frame = pd.DataFrame(new_homes, columns=['building_id'])
    result_set = pd.merge(new_homes_frame, dset.buildings, left_on='building_id', right_index=True, how='left')[['building_id','zone_id']]
    result_set["employees"] = pd.merge(result_set, dset.establishments, left_index=True, right_index=True)['employees'].values
    table = dset.establishments # need to go back to the whole dataset
    #table[depvar].ix[new_homes.index] = new_homes.values.astype('int32')
    table.loc[result_set.index, "building_id"] = -1
    table.loc[result_set.index, "zone_id"] = -1
    table.loc[result_set.index,"building_id"] = result_set.building_id.values
    table.loc[result_set.index,"zone_id"] = result_set.zone_id
    #table["zone_id"] = pd.merge(table, result_set, on='building_id', how='left')['zone_id'].values
    #table["zone_id"] = pd.merge(table, dset.buildings, left_on='building_id', right_index=True, how='left')["zone_id_y"].values
    dset.store_attr(output_varname,year,copy.deepcopy(table[depvar]))