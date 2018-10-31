##########################################################################################
# Script to find all grouped but non-existing entities
#
# https://community.home-assistant.io/t/script-to-find-items-that-no-longer-exist/56146/52
# original author: https://community.home-assistant.io/u/NigelL
# customizing, further tweaking and pushing it a bit by https://community.home-assistant.io/u/Mariusthvdb/
##########################################################################################
# set ignore_items and ignore_domains in the yaml file calling the script
# script:
#   scan_ghosts:
#     alias: Scan Ghosts
#     sequence:
#       - service: python_script.scan_ghosts
#         data:
#           ignore_items:
#             - updater.updater
#             - sensor.ghosts_sensor
#             - sensor.ghosts_badge
#             - sensor.orphans_sensor
#             - sensor.orphans_badge
#             - python_script.scan_for_orphans
#           ignore_domains:
#             - media_player
#             - remote
#
##########################################################################################
# Codes for text_colors declared in 
# Custom card: /custom_ui/state-card-value_only.html
##########################################################################################

#      case "*": return "bold";
#      case "/": return "italic";
#      case "!": return "red";
#      case "+": return "green";
#      case "=": return "yellow";
#      case "%": return "grey";
#      case "$": return "brown";
#      case "#": return "blue";
#      default:  return "normal";
##########################################################################################

def process_group_entities(group, grouped_entities, hass, logger, process_group_entities,\
                             processed_groups, ignore_domains, ignore_items):
#  logger.info("processing group {}, currently {} grouped items".format(group.entity_id, len(grouped_entities)))

    processed_groups.append(group.entity_id)
    for e in group.attributes['entity_id']:
        domain = e.split('.')[0]
        if domain == 'group':
            g = hass.states.get(e)
            if (g is not None) and (g.entity_id not in processed_groups):
                process_group_entities(g, grouped_entities, hass, logger, process_group_entities,\
                                processed_groups, ignore_domains, ignore_items)
        else:
            if (domain not in ignore_domains):
                if not e in grouped_entities:
                    grouped_entities[e] = set()
                    grouped_entities[e].add(group.entity_id)
      
#  logger.info("finishing group {}, currently {} grouped items".format(group.entity_id, \ len(grouped_entities)))
  
def scan_ghosts(hass, logger, data, process_group_entities):
    target_group=data.get('target_group','group.ghosts')
    show_as_view = data.get('show_as_view', False)
    use_custom_ui = data.get('use_custom_ui', True)
    ignore_items = data.get('ignore_items',[])
    ignore_domains = data.get('ignore_domains',[])
    show_if_empty = data.get('show_if_empty', False)
    min_items_to_show = data.get('min_items_to_show', 0)
    real_entities = set(ignore_items)
    grouped_entities = {}
    processed_groups=[]
  
    for s in hass.states.all():
        domain = s.entity_id.split('.')[0]
        if domain != 'group':
            real_entities.add(s.entity_id)
        else:
            if (('view' not in s.attributes) or
                ( s.attributes['view'] == False)):
                    real_entities.add(s.entity_id)
                    process_group_entities(s,grouped_entities,hass,logger, \
                        process_group_entities,processed_groups,ignore_domains, \
                        ignore_items)

    logger.info('{} real entities'.format(len(real_entities)))
    logger.info('{} grouped entities'.format(len(grouped_entities)))
    logger.info('{} groups processed'.format(len(processed_groups)))
    results = grouped_entities.keys() - real_entities
    logger.info('{} entities to list'.format(len(results)))
    entity_ids=[]

##    if (use_custom_ui): ## show card

    busted=""
    busted_badge=""

    if (len(results)) > min_items_to_show or show_if_empty:
        visible = True
        for e in results:
            line = '{} in: {}'.format(e, ','.join(grouped_entities[e]))
            busted = '{}!- {}\n'.format(busted,line)
            busted_badge = '{}{}\n'.format(busted_badge,line)
            friendly_name_badge = len(results)
    else:
        visible = False
        busted = '!- All busted, {} Ghosts found!\n'.format(len(results))
        busted_badge = 'No Ghosts found\n'
        friendly_name_badge = 'All busted'

    ignore_items_unlist = ', '.join(ignore_items)
    ignore_domains_unlist = ', '.join(ignore_domains)


    ghost_card = '*=========== Ghosts ===========\n' \
                 '{}\n' \
                 '*========= Entity count =========\n' \
                 '!- {} entities to list\n' \
                 '#- {} real entities\n' \
                 '+- {} grouped entities\n' \
                 '+- {} groups processed\n' \
                 '*========== Settings ===========\n' \
                 '/- targetting group: {}\n' \
                 '$- ignoring {} items:\n' \
                 '%|-> {}\n' \
                 '$- ignoring {} domains:\n' \
                 '%|-> {}' \
                 .format(busted,
                         len(results),
                         len(real_entities),
                         len(grouped_entities),
                         len(processed_groups),
                         target_group,
                         len(ignore_items),
                         ignore_items_unlist,
                         len(ignore_domains),
                         ignore_domains_unlist)

    hass.states.set('sensor.ghosts_sensor', len(results), {
        'custom_ui_state_card': 'state-card-value_only',
        'text': ghost_card,
#        'unit_of_measurement': 'ghosts'
         })

#    else: ##show group with found ghosts:
    counter=0
    for e in results:
        name = 'left_entity.ghost{}'.format(counter)
        parent = 'In: {}'.format(','.join(grouped_entities[e]))
        hass.states.set(name, parent, {'friendly_name':e, 'icon': 'mdi:ghost'})
        entity_ids.append(name)
        counter = counter +1

    service_data = {'object_id': 'ghosts','name': 'Ghosts',
                    'view': show_as_view,'icon': 'mdi:ghost',
                    'control': 'hidden','entities': entity_ids,
                    'visible': visible }

    hass.services.call('group', 'set', service_data, False)

#   show badge
    hass.states.set('sensor.ghosts_badge', len(results), {
        'text': busted_badge,
        'unit_of_measurement': 'Ghosts',
        'friendly_name': friendly_name_badge,
        'entity_picture': '/local/badges/ghosts.png'
         })

scan_ghosts(hass, logger, data, process_group_entities)
