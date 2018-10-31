##########################################################################################
# Script to find all ungrouped but existing entities
#
# https://community.home-assistant.io/t/script-to-find-all-ungrouped-items/55774/117
# original author: https://community.home-assistant.io/u/NigelL
# customizing, further tweaking and pushing it a bit by https://community.home-assistant.io/u/Mariusthvdb/
# ##########################################################################################
# set ignore_domains in the yaml file calling the script
#  scan_orphans:
#    alias: Scan ungrouped Orphans
#    sequence:
#      - service: python_script.scan_orphans
#        data:
#          ignore_items:
#            - sensor.ghosts_sensor
#            - sensor.orphans_sensor
#            - sensor.orphans_badge
#          ignore_domains:
#            - scene
#            - zwave
#            - weblink
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
##########################################################################################

def scan_orphans(hass, logger, data):
    target_group = data.get("target_group", "group.orphans")
    show_as_view = data.get("show_as_view", False)
    use_custom_ui = data.get("use_custom_ui", True)
    ignore_items = data.get("ignore_items",[])
    ignore_domains = data.get("ignore_domains", [])
    show_if_empty = data.get("show_if_empty", False)
    min_items_to_show = data.get("min_items_to_show", 1)

    logger.info("ignoring {} item(s)".format(len(ignore_items)))
    logger.info("ignoring {} domain(s)".format(len(ignore_domains)))
    logger.info("Targetting group {}".format(target_group))

    entity_ids = []
    groups = []

    for s in hass.states.all():
        state = hass.states.get(s.entity_id)
        domain = state.entity_id.split(".")[0]

        if state.entity_id in ignore_items:
            continue # Ignore this entity, and go to the next one

        if (domain not in ignore_domains):
            if (domain != "group"):
                if (("hidden" not in state.attributes) or
                        (state.attributes["hidden"] == False)):
                    entity_ids.append(state.entity_id)
            else:
                if (("view" not in state.attributes) or
                        (state.attributes["view"] == False)):
                    entity_ids.append(state.entity_id)

        if (domain == "group") and (state.entity_id != target_group):
            groups.append(state.entity_id)

    logger.info("==== Entity count ====")
    logger.info("{0} entities".format(len(entity_ids)))
    logger.info("{0} groups".format(len(groups)))

    for groupname in groups:
        group = hass.states.get(groupname)
        for a in group.attributes["entity_id"]:
            if a in entity_ids:
                entity_ids.remove(a)

    if (len(entity_ids)) > min_items_to_show or show_if_empty:
        visible = True
    else:
        visible = False

#  if (use_custom_ui): #, show card
    left_overs=""
    for a in entity_ids:
        left_overs = "{}!- {}\n".format(left_overs,a)
        left_overs_badge = "\n".join(entity_ids)
    ignore_items_unlist = ', '.join(ignore_items)
    ignore_domains_unlist = ', '.join(ignore_domains)

    left_over_card = '*=========== Orphans ===========\n'\
                     '{}'\
                     '*========== Entity count =========\n'\
                     '!- {} entities to list\n'\
                     '+- {} groups processed\n'\
                     '*=========== Settings ===========\n'\
                     '/- targetting group: {}\n'\
                     '$- ignoring {} items:\n' \
                     '%|-> {}\n'\
                     '$- ignoring {} domains:\n' \
                     '%|-> {}'\
                     .format(left_overs,
                             len(entity_ids),
                             len(groups),
                             target_group,
                             len(ignore_items),
                             ignore_items_unlist,
                             len(ignore_domains),
                             ignore_domains_unlist)

    hass.states.set('sensor.orphans_sensor', len(entity_ids), {
        'custom_ui_state_card': 'state-card-value_only',
        'text': left_over_card,
      # 'unit_of_measurement': 'Orphans'
        })

#  else: ##show group with found orphans:
    service_data = {'object_id': 'orphans', 'name': 'Orphans',
                    'view': show_as_view, 'icon': 'mdi:magnify',
                    'control': 'hidden', 'entities': entity_ids,
                    'visible': True}

    hass.services.call('group', 'set', service_data, False)

# show badge
    hass.states.set('sensor.orphans_badge', len(entity_ids), {
        'text': left_overs_badge,
        'unit_of_measurement': 'Orphans',
        'friendly_name': len(entity_ids),
        'entity_picture': '/local/badges/orphans.png'
         })

scan_orphans(hass, logger, data)