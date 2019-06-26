# ## Process the SDG Data Items
# The purpose of this notebook is to illustrate how to use the SDG Metadata API in conjunction with local CSV files to
# publish spatial data to ArcGIS Online.  While this example has some elements that are specific to the UNSD workflow it
# is generic enough to show how to loop and use the API for publishing.  You may to need add or update workflows around
# publishing to meet your exact needs and working environments.

# ### Import python libraries
import copy
# used to prompt for user input
# when using this script internally, you may remove this and simply hard code in your username and password
import getpass
import json
import os
import re
import sys
import time
import traceback
import urllib
import urllib.request as request
import urllib.request as urlopen
from datetime import datetime
import copy
#import requests

# this helps us do some debugging within the Python Notebook
# another optional component
from IPython.display import display
from arcgis.gis import GIS

# Initialize the application and set the global variables
def main():
    # set up the global information and variables
    global data_dir
    global metadata_dir
    global open_data_group
    global failed_series
    global online_username
    global gis_online_connection
    global layer_json_data
    global layer_geojson_data
    global user_items

    # ### Create a connection to your ArcGIS Online Organization
    # This will rely on using the ArcGIS API for python to connect to your ArcGIS Online Organization to publish and
    # manage data.  For more information about this python library visit the developer
    # resources at [https://developers.arcgis.com/python/](https://developers.arcgis.com/python/]
    online_username = "nso_admin"# input('Username: ')
    online_password = "gis@nso2018" #getpass.getpass('Password: ')
    online_connection = "https://www.arcgis.com"
    gis_online_connection = GIS(online_connection, online_username, online_password)

    # open_data group_id:  Provide the Group ID from ArcGIS Online the Data will be shared with
    # This should be a staging group to ge the data ready for publishing
    open_data_group_id = '9748fdbbb47143b98dd50bd21bebd94d'
    open_data_group = gis_online_connection.groups.get(open_data_group_id)

    # Get information from the local branch
    data_dir = r"FIS4SDG/csv/"
    metadata_dir = r"FIS4SDG"
    
    # for search and updates access may be needed for the users items
    user = gis_online_connection.users.get(online_username)
    user_items = user.items(folder='Open Data', max_items=800)

    #run the primary function to update and publish the SDG infomation to a user content area
    failed_series = []
    layer_geojson_data = json.load(open("./nso.geojson"))
    #process_sdg_information(goal_code=[1],target_code="1.1",indicator_code="1.1.1",series_code="SI_POV_DAY1", property_update_only=True, update_symbology=True, run_cleanup=False, update_sharing=False)
    #goal_code=3,target_code="3.2", indicator_code="3.2.1",  
    process_sdg_information(run_cleanup=True)


    print(failed_series)
    return

def get_indicator_data(goal, target, indicatorID, year):
    try:
        api_url = "http://sdg.gov.mn/SDG_WebAPI/DataAimagSoum/"+indicatorID+"/" + str(year)
        req = request.Request(api_url)
        response = urlopen.urlopen(req)
        response_bytes = response.read()
        responseData = json.loads(response_bytes.decode('UTF-8'))
        
        x = responseData['Data']['ResponseData']['DataAimagSoum']
        print(x)
        
        variable_url ="http://sdg.gov.mn/SDG_WebAPI/VariableDataList/"+goal+"/G/EN"
        req = request.Request(variable_url)
        response = urlopen.urlopen(req)
        response_bytes = response.read()
        responseData = json.loads(response_bytes.decode('UTF-8'))    
        g = responseData['Data']['ResponseData']['VariableList']
        print (g)
        goalID = g['GoalID']
        goalCode = g['Code']
        goalLabel = g['Label']

        for t in g['VariableList']:
            if t['Code'] == 'Target ' + target:
                targetID = t['Code']
                targetLabel = t['Label']
                
                for i in t['VariableList']:
                    if i['Code'] == indicatorID:
                        indicatorLabel = i['Label']
                        break

        for row in x:
            row['REF_AREA_DESC'] = row.pop('AimagName')
            row['REF_AREA'] = row.pop('aimagCode')
            row['OBS_VALUE'] = row.pop('data')
            row['TIME_PERIOD'] = row.pop('yearCode')
            row['GOAL_ID'] = goalID
            row['GOAL_CODE'] = goalCode
            row['GOAL_LABEL'] = goalLabel
            row['TARGET_ID'] = targetID
            row['TARGET_LABEL'] = targetLabel
            row['INDICATOR_ID'] = indicatorID
            row['INDICATOR_LABEL'] = indicatorLabel

            #Remove any other values
            row.pop('soumCode', None)

        print(x)
        return x
    except:
        return None

#This will only clean out data in your Open Data Site
def cleanup_site():
    user = gis_online_connection.users.get(online_username)
    #user_items = user.items(folder='Open Data', max_items=800)
    for item in user_items:
        print('deleting item ' + item.title)
        item.delete()
    return

def get_series_tags(goal_metadata=None, indicator_code=None, target_code=None):
    try:
        for target in goal_metadata["targets"]:
            if target["target"] == target_code:
                for indicator in target["indicators"]:
                    if indicator["indicator"] == indicator_code:
                        print(indicator["series"][0]["tags"])
                        return indicator["indicator"]["tags"]
        return []
    except:
        traceback.print_exc()
        return []

def update_item_categories(item,goal,target,group=False):
    try:
        if group:
            update_url = gis_online_connection._url + "/sharing/rest/community/groups/" + open_data_group.id +"/updateItems"
        else:
            update_url = gis_online_connection._url + "/sharing/rest/content/updateItems"

        items = [{item["id"]:{"categories":["/Categories/Goal " + str(goal) + "/Target " + str(target)]}}]
        update_params = {'f': 'json', 'token': gis_online_connection._con.token, 'items': json.dumps(items)}
        data = parse.urlencode(update_params).encode()
        req =  request.Request(update_url, data=data) # this will make the method "POST"
        resp = request.urlopen(req)

        #r = requests.post(update_url, data=update_params)
        update_json_data = json.loads(resp.content.decode("UTF-8"))
        print(update_json_data)
    except:
        traceback.print_exc()
        return []

# ## Process the SDG Information
# ### process_sdg_information
# Allow the SDG information to be processed either as a batch of by individual series of information
# This function is where the majority of the work will happen. Here is a basic outline of the steps we will take:
# - Build out the item card information from the Metadata API and additional information
# - Create an Group in ArcGIS Online for the Goal if needed, otherwise update the property information
# - If exists, update and move to Open Data Group
# - Publish the CSV File (if the property_update_only flag is False)
# - If it doesn't exist, publish as a new Item then move to the Open Data Group
#
# ##### goal_code (default None):  Indvidual goal code.  This will process this goal and all the children targets as well
# process_sdg_information(goal_code='1')
# ##### indicator_code (default None):  Individual indicator code.  This will process this indicator and all the children targets as well
# process_sdg_information(goal_code='1',indicator_code='1.1')
# ##### target_code (default None):  Individual Target code.  This will process this target code only
# process_sdg_information(goal_code='1',indicator_code='1.1',target_code='1.1.1')
# ##### series_code (default None):  Individual Series code.  This will process this series code only
# process_sdg_information(goal_code='1',indicator_code='1.1',target_code='1.1.1',series_code='SI_POV_DAY1')
# ##### property_update_only (default False):  If True this will only update the metadata in the item card and will not process the actual data sources
# process_sdg_information(goal_code='1',indicator_code='1.1',target_code='1.1.1',series_code='SI_POV_DAY1',property_update_only=True)

def process_sdg_information(goal_code=None, indicator_code=None, target_code=None, series_code=None,
                            property_update_only=False, update_symbology=False, run_cleanup=False, update_sharing=True):
    try:

        if run_cleanup:
            # This will delete everything in your staging folder for Open Data. Use with caution, with a wise and clear head!!!!
            cleanup_site()

        sdg_metadata = get_metadata()
        for goal in get_goal_information():
            # Determine if we are processing this query Only process a specific series code
            if goal_code is not None and int(goal["code"]) is not goal_code:
                continue

            # Get the Thumbnail from the SDG API
            for goal_item in sdg_metadata:
                if goal_item["goal"] == int(goal["code"]):
                    goal_metadata = goal_item
                    break

            if goal_metadata is None:
                continue

            # if a thumbnail was not found use a default thumbnail for icon
            if "icon_url_sq" in goal_metadata:
                thumbnail = goal_metadata["icon_url_sq"]
            else:
                thumbnail = "http://undesa.maps.arcgis.com/sharing/rest/content/items/aaa0678dba0a466e8efef6b9f11775fe/data"

            thumbnail = 'https://raw.githubusercontent.com/UNStats/FIS4SDGs/master/globalResources/sdgIcons120x120/SDG03.jpg'
            # Create a Group for the Goal
            group_goal_properties = dict()
            group_goal_properties["title"] = "SDG " + goal["code"]
            group_goal_properties["snippet"] = goal["title"]
            group_goal_properties["description"] = goal["description"]
            group_goal_properties["tags"] = [group_goal_properties["title"]]
            group_goal_properties["thumbnail"] = thumbnail

            # Iterate through each of the targets
            for target in goal["targets"]:
                # Determine if we are processing this query Only process a specific target code
                if target_code is not None and target["code"] != target_code:
                    continue

                group_target_properties = dict()
                group_target_properties["tags"] = ["Target " + target["code"]]

                # Iterate through each of the indicators
                for indicator in target["indicators"]:
                    # Allow processing a single indicator
                    if indicator_code and not indicator["code"] == indicator_code:
                        continue

                    process_indicator = dict()
                    process_indicator["name"] = "Indicator " + indicator["code"]  # eg. Indicator 1.1.1
                    process_indicator["tags"] = [process_indicator["name"]]
                    process_indicator["snippet"] = indicator["code"] + ": " + indicator["description"]
                    process_indicator["title"] = indicator["code"] + ": " + indicator["description"]
                    process_indicator["description"] = "<p><strong>Indicator " + indicator["code"] + ": </strong>" + \
                        indicator["description"] + "</p>" + "</p><p><strong>Target " + \
                        target["code"] + ": </strong>" + \
                        target["description"] + "</p>" + "<p>" + \
                        goal["description"] + "</p>"

                    process_indicator["credits"] = "National Statistics Office of Mongolia"
                    process_indicator["thumbnail"] = thumbnail
                    final_tags = group_goal_properties["tags"] + group_target_properties["tags"] + \
                                    process_indicator["tags"]
                    process_indicator["tags"] = final_tags
                    indicator_data = get_indicator_data(goal["code"], target["code"], indicator["code"], 0)
                    if indicator_data is not None:
                        indicator_geojson = {"type": "FeatureCollection", "features": []}
                        for data in indicator_data:
                            for feature in layer_geojson_data["features"]:
                                if feature["properties"]["IDtxt"] == data["REF_AREA"]:
                                    indicator_feature = copy.deepcopy(feature)
                                    indicator_feature["properties"] = data
                                    indicator_geojson["features"].append(indicator_feature)
                                    break

                        #find this record in geojson
                        if(indicator_geojson["features"].count != 0):
                            geojsonfile = process_indicator["name"].replace(".","").replace(" ","") + ".geojson"
                            with open(geojsonfile, 'w') as outfile:
                                json.dump(indicator_geojson, outfile)
                            
                            publish_geojson(process_indicator["name"].replace(".","").replace(" ",""),geojsonfile, process_indicator,thumbnail)
    except:
        traceback.print_exc()

# ### Get the JSON Data from the UN SDG Metadata API
# The SDG Metadata API is designed to  retrieve information and metadata on the
# [Sustainable Development Goals](http://www.un.org/sustainabledevelopment/sustainable-development-goals/).
# The Inter-agency Expert Group on SDG Indicators released a series of PDFs that includes metadata for each Indicator.
# Those PDFs can be downloaded [here](http://unstats.un.org/sdgs/iaeg-sdgs/metadata-compilation/).
# The metadata API is an Open Source project maintained by the UN Statisitics division and be be accessed on
# [github](https://github.com/UNStats-SDGs/sdg-metadata-api)

def get_goal_information():
    url = "https://unstats.un.org/SDGAPI/v1/sdg/Goal/List?includechildren=true"
    req = request.Request(url)
    response = urlopen.urlopen(req)
    response_bytes = response.read()
    json_data = json.loads(response_bytes.decode("UTF-8"))
    return json_data

# ### Find the Online Item
def find_online_item(title, full_title=None, force_find=True):
    try:
        if full_title is None:
            full_title = title

        # Search for this ArcGIS Online Item
        query_string = "title:'{}' AND owner:{}".format(title, online_username)
        print('Searching for ' + full_title)
        search_results = gis_online_connection.content.search(query_string)

        if search_results:
            for search_result in search_results:
                if search_result["title"] == full_title:
                    return search_result


        #If the Item was not found in the search but it should exist use Force Find to loop all the users items (this could take a bit)
        if force_find:
            user = gis_online_connection.users.get(online_username)
            #user_items = user.items(folder='Open Data', max_items=800)
            for item in user_items:
                if item["title"] == full_title:
                    return item

        return None
    except:
        print("Unexpected error:", sys.exc_info()[0])
        return None

# ### Analyze the CSV file
# Using the ArcGIS REST API `analyze` endpoint, we can prepare the CSV file we are going to use before publishing it to
# ArcGIS Online. This will help us by returning information about the file inlcuding fields as well as sample records.
# This step will also lead into future steps in the publishing process.
# More info about the analyze endpoint can be found
# [here](https://developers.arcgis.com/rest/users-groups-and-items/analyze.htm).

def analyze_csv(item_id):
    try:
        sharing_url = gis_online_connection._url + "/sharing/rest/content/features/analyze"
        analyze_params = {'f': 'json', 'token': gis_online_connection._con.token,
                          'sourceLocale': 'en-us',
                          'filetype': 'geojson', 'itemid': item_id}

        data = parse.urlencode(analyze_params).encode()
        req =  request.Request(sharing_url, data=data) # this will make the method "POST"
        r = request.urlopen(req)

        #r = requests.post(sharing_url, data=analyze_params)
        analyze_json_data = json.loads(r.content.decode("UTF-8"))
        for field in analyze_json_data["publishParameters"]["layerInfo"]["fields"]:
            field["alias"] = set_field_alias(field["name"])

            # Indicator is coming in as a date Field make the correct
            if field["name"] == "indicator":
                field["type"] = "esriFieldTypeString"
                field["sqlType"] = "sqlTypeNVarchar"

        # set up some of the layer information for display
        analyze_json_data["publishParameters"]["layerInfo"]["displayField"] = "geoAreaName"
        return analyze_json_data["publishParameters"]
    except:
        print("Unexpected error:", sys.exc_info()[0])
        return None


def generate_renderer_infomation(feature_item, statistic_field="latest_value", color=None):
    try:
        if len(color) == 3:
            color.append(130)

        layer_json_data = json.load(open(metadata_dir + "/layerinfo.json"))
        #get the min/max for this item
        visual_params = layer_json_data["layerInfo"]
        definition_item = feature_item.layers[0]

        #get the min/max values
        out_statistics= [{"statisticType": "max","onStatisticField": "latest_value", "outStatisticFieldName": "latest_value_max"},
                        {"statisticType": "min","onStatisticField": "latest_value", "outStatisticFieldName": "latest_value_min"}]
        feature_set = definition_item.query(where='1=1',out_statistics=out_statistics)

        max_value = feature_set.features[0].attributes["latest_value_max"]
        min_value = feature_set.features[0].attributes["latest_value_min"]
        visual_params["drawingInfo"]["renderer"]["visualVariables"][0]["minDataValue"] = min_value
        visual_params["drawingInfo"]["renderer"]["visualVariables"][0]["maxDataValue"] = max_value

        visual_params["drawingInfo"]["renderer"]["authoringInfo"]["visualVariables"][0]["minSliderValue"] = min_value
        visual_params["drawingInfo"]["renderer"]["authoringInfo"]["visualVariables"][0]["maxSliderValue"] = max_value
        visual_params["drawingInfo"]["renderer"]["classBreakInfos"][0]["symbol"]["color"] = color
        visual_params["drawingInfo"]["renderer"]["transparency"] = 25

        definition_update_params = definition_item.properties
        definition_update_params["drawingInfo"]["renderer"] = visual_params["drawingInfo"]["renderer"]
        if "editingInfo" in definition_update_params:
            del definition_update_params["editingInfo"]
        definition_update_params["capabilities"] = "Query, Extract"
        print('Update Feature Service Symbology')
        definition_item.manager.update_definition(definition_update_params)

        return
    except:
        print("Unexpected error in generate_renderer_infomation:", sys.exc_info()[0])
        return None

# ### Publish the CSV file
# This function is where the majority of the work will happen. Here is a basic outline of the steps we will take:
# - Begin by asking for the path to the CSV file itself
# - Check if the CSV file exists
# - If exists, update and move to Open Data Folder under the owner content
# - If it doesn't exist, publish as a new Item then move to the Open Data Group
def publish_geojson(title,geojson_file, item_properties, thumbnail, property_update_only=False, color=[169,169,169]):
    # Do we need to publish the hosted feature service for this layer
    try:
        # check if service name is available if not update the link
        #series_num = 1
        #while not gis_online_connection.content.is_service_name_available(service_name= series_title, service_type = 'featureService'):
        #    series_title = series["code"] + "_" + indicator["code"].replace(".","") + "_" + series["release"].replace('.', '') + "_" + str(series_num)
        #    series_num += 1

        #file = os.path.join(data_dir, series["code"] + "_cube.pivot.csv")
        if os.path.isfile(geojson_file):
            geoJSONitem_properties = copy.deepcopy(item_properties)
            geoJSONitem_properties["title"] = title
            geoJSONitem_properties["name"] = title
            geoJSONitem_properties["type"] = "GeoJson"
            geoJSONitem_properties["url"] = ""

            # Does this CSV already exist
            geoJSONitem = find_online_item(geoJSONitem_properties["title"])
            if geoJSONitem is None:
                print('Adding GeoJSON File to ArcGIS Online....')
                geoJSONitem = gis_online_connection.content.add(item_properties=geoJSONitem_properties, thumbnail=thumbnail,
                                                             data=geojson_file)
                if geoJSONitem is None:
                    return None

                # publish the layer if it was not found
                print('Analyze Feature Service....')
                #publish_parameters = analyze_csv(geoJSONitem["id"])
                #if publish_parameters is None:
                #    return None
                #else:
                publish_parameters = {"name": title, "layerInfo": {"name": title}}
                print('Publishing Feature Service....')
                geoJSONlyr = geoJSONitem.publish(publish_parameters=publish_parameters)

                    # Update the layer infomation with a basic rendering based on the Latest Value
                    # use the hex color from the SDG Metadata for the symbol color
                    #generate_renderer_infomation(geoJSONlyr,statistic_field="latest_value", color=color)
            else:
                # Update the Data file for the CSV File
                geoJSONitem.update(item_properties=geoJSONitem_properties, thumbnail=thumbnail, data=geojson_file)
                # Find the Feature Service and update the properties
                geoJSONlyr = find_online_item(item_properties["title"])

            # Move to the Open Data Folder
            if geoJSONitem["ownerFolder"] is None:
                print('Moving CSV to Open Data Folder')
                geoJSONitem.move("Open Data")

            if geoJSONlyr is not None:
                print('Updating Feature Service metadata....')
                geoJSONlyr.update(item_properties=item_properties, thumbnail=thumbnail)

                if geoJSONlyr["ownerFolder"] is None:
                    print('Moving Feature Service to Open Data Folder')
                    geoJSONlyr.move("Open Data")

                return geoJSONlyr
            else:
                return None
        else:
            return None
    except:
        print("Unexpected error:", sys.exc_info()[0])
        return None


# ### Collect SDG Metadata
# For each new Item published, we can use the SDG Metadata API to return all the metadata associated with that layer
def get_metadata():
    try:
        metadata_json_data = json.load(open(metadata_dir + "/metadataAPI.json"))
        return metadata_json_data
    except:
        print("Unexpected error:", sys.exc_info()[0])
        return None


#Translate the names found in the Service Information for the alias fields
def set_field_alias(field_name):
    if field_name == "series_release":
        return "Series Release"
    if field_name == "series_code":
        return "Series Code"
    if field_name == "series_description":
        return "Series Description"
    if field_name == "geoAreaCode":
        return "Geographic Area Code"
    if field_name == "geoAreaName":
        return "Geographic Area Name"
    if field_name == "Freq":
        return "Frequency"
    if field_name == "latest_year":
        return "Latest Year"
    if field_name == "latest_value":
        return "Latest Value"
    if field_name == "latest_source":
        return "Latest Source"
    if field_name == "latest_nature":
        return "Latest Nature"
    if field_name == "last_5_years_mean":
        return "Mean of the Last 5 Years"
    if field_name == "ISO3CD":
        return "ISO3 Code"
    else:
        return field_name.capitalize().replace("_", " ")

# ### Create a Group for each SDG Goal
# You can create a Group within your ArcGIS Online Organization for each SDG. As you publish Items, you can share them to the relevant Group(s). 
# This function will create the Group, query the SDG Metadata API to return the Title, Summary, Description, Tags, and Thumbnail for that particular SDG.
def create_group(group_info):
    try:
        # Add the Service Definition to the Enterprise site
        item_properties = dict({
            "title": group_info["title"],
            "snippet": group_info["snippet"],
            "description": group_info["description"],
            "tags": ", ".join([group_info["title"], "Open Data", "Hub"]),
            "thumbnail": group_info["thumbnail"],
            "isOpenData": True,
            "access": "public",
            "isInvitationOnly": True,
            "protected": True
        })

        # Check if there is a group here
        query_string = "title:'{}' AND owner:{}".format("SDG Open Data", online_username)
        search_results = gis_online_connection.groups.search(query_string)
        if not search_results:
            # Update the group information
            group = gis_online_connection.groups.create_from_dict(item_properties)
            display(group)
            return group
        else:
            for search_result in search_results:
                if search_result["title"] == group_info["title"]:
                    search_result.update(title=group_info["title"], tags=group_info["tags"],
                                         description=group_info["description"],
                                         snippet=group_info["snippet"], access="Public",
                                         thumbnail=group_info["thumbnail"])
                    return search_result
            # the group was not in the returned search results so create now
            group = gis_online_connection.groups.create_from_dict(item_properties)
            display(group)
            return group
    except:
        traceback.print_exc()


#set the primary starting point
if __name__ == "__main__":
    main()      
