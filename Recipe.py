import sqlite3
import uuid
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from geopy.distance import geodesic
import webbrowser
from urllib.parse import urlencode
import re
import json
from tqdm import tqdm  # For command-line progress bars (Optional: Remove if not needed)

# ---------------------------
# Database Setup and Functions
# ---------------------------

# Database connections
conn_recipes = sqlite3.connect('recipes.db')
cursor_recipes = conn_recipes.cursor()

conn_shops = sqlite3.connect('shops.db')
cursor_shops = conn_shops.cursor()

# Create tables if they don't exist
# Recipes Database
cursor_recipes.execute('''
CREATE TABLE IF NOT EXISTS Recipes (
    recipe_id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_name TEXT NOT NULL UNIQUE
)
''')

cursor_recipes.execute('''
CREATE TABLE IF NOT EXISTS RecipeIngredients (
    recipe_id INTEGER,
    ingredient_name TEXT,
    quantity REAL,
    unit TEXT,
    FOREIGN KEY (recipe_id) REFERENCES Recipes(recipe_id)
)
''')

# Shops Database
cursor_shops.execute('''
CREATE TABLE IF NOT EXISTS Shops (
    shop_id TEXT PRIMARY KEY,
    shop_name TEXT NOT NULL UNIQUE,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL
)
''')

cursor_shops.execute('''
CREATE TABLE IF NOT EXISTS ShopInventory (
    shop_id TEXT,
    ingredient_name TEXT,
    quantity REAL,
    unit TEXT,
    FOREIGN KEY (shop_id) REFERENCES Shops(shop_id)
)
''')

conn_recipes.commit()
conn_shops.commit()


# Functions for database operations

# Recipes Functions
def add_recipe(recipe_name, ingredients):
    try:
        cursor_recipes.execute('INSERT INTO Recipes (recipe_name) VALUES (?)', (recipe_name,))
        recipe_id = cursor_recipes.lastrowid
        for ingredient in ingredients:
            cursor_recipes.execute('''
            INSERT INTO RecipeIngredients (recipe_id, ingredient_name, quantity, unit)
            VALUES (?, ?, ?, ?)
            ''', (recipe_id, ingredient['name'], ingredient['quantity'], ingredient['unit']))
        conn_recipes.commit()
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Recipe '{recipe_name}' already exists.")


def get_all_recipes():
    cursor_recipes.execute('SELECT recipe_id, recipe_name FROM Recipes')
    return cursor_recipes.fetchall()


def update_recipe(recipe_id, new_name, new_ingredients):
    try:
        cursor_recipes.execute('UPDATE Recipes SET recipe_name = ? WHERE recipe_id = ?', (new_name, recipe_id))
        cursor_recipes.execute('DELETE FROM RecipeIngredients WHERE recipe_id = ?', (recipe_id,))
        for ingredient in new_ingredients:
            cursor_recipes.execute('''
            INSERT INTO RecipeIngredients (recipe_id, ingredient_name, quantity, unit)
            VALUES (?, ?, ?, ?)
            ''', (recipe_id, ingredient['name'], ingredient['quantity'], ingredient['unit']))
        conn_recipes.commit()
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Recipe name '{new_name}' already exists.")


def delete_recipe(recipe_id):
    cursor_recipes.execute('DELETE FROM RecipeIngredients WHERE recipe_id = ?', (recipe_id,))
    cursor_recipes.execute('DELETE FROM Recipes WHERE recipe_id = ?', (recipe_id,))
    conn_recipes.commit()


# Shops Functions
def add_shop(shop_name, latitude, longitude, inventory):
    try:
        shop_id = str(uuid.uuid4())
        cursor_shops.execute('''
        INSERT INTO Shops (shop_id, shop_name, latitude, longitude)
        VALUES (?, ?, ?, ?)
        ''', (shop_id, shop_name, latitude, longitude))
        for item in inventory:
            cursor_shops.execute('''
            INSERT INTO ShopInventory (shop_id, ingredient_name, quantity, unit)
            VALUES (?, ?, ?, ?)
            ''', (shop_id, item['name'], item['quantity'], item['unit']))
        conn_shops.commit()
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Shop name '{shop_name}' already exists.")


def get_all_shops():
    cursor_shops.execute('SELECT shop_id, shop_name FROM Shops')
    return cursor_shops.fetchall()


def update_shop(shop_id, new_name, new_latitude, new_longitude, new_inventory):
    try:
        cursor_shops.execute('''
        UPDATE Shops
        SET shop_name = ?, latitude = ?, longitude = ?
        WHERE shop_id = ?
        ''', (new_name, new_latitude, new_longitude, shop_id))
        cursor_shops.execute('DELETE FROM ShopInventory WHERE shop_id = ?', (shop_id,))
        for item in new_inventory:
            cursor_shops.execute('''
            INSERT INTO ShopInventory (shop_id, ingredient_name, quantity, unit)
            VALUES (?, ?, ?, ?)
            ''', (shop_id, item['name'], item['quantity'], item['unit']))
        conn_shops.commit()
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", f"Shop name '{new_name}' already exists.")


def delete_shop(shop_id):
    cursor_shops.execute('DELETE FROM ShopInventory WHERE shop_id = ?', (shop_id,))
    cursor_shops.execute('DELETE FROM Shops WHERE shop_id = ?', (shop_id,))
    conn_shops.commit()


# Geospatial Function
def calculate_distance(coord1, coord2):
    return geodesic(coord1, coord2).kilometers


# Enhanced Shop Finding Function
def find_nearby_shops_for_recipe(recipe_id, user_location, radius_km):
    """
    Optimized version of finding nearby shops for a recipe using bulk data retrieval.
    """
    try:
        # Step 1: Get required ingredients
        cursor_recipes.execute('''
            SELECT ingredient_name, quantity, unit FROM RecipeIngredients WHERE recipe_id = ?
        ''', (recipe_id,))
        required_ingredients = cursor_recipes.fetchall()

        if not required_ingredients:
            return {'type': 'no_ingredients', 'message': 'No ingredients found for the selected recipe.'}

        # Convert to dictionary for easy access
        ingredients_needed = {name: {'quantity': qty, 'unit': unit} for name, qty, unit in required_ingredients}

        # Step 2: Get all shops
        cursor_shops.execute('SELECT shop_id, shop_name, latitude, longitude FROM Shops')
        all_shops = cursor_shops.fetchall()

        # Step 3: Identify nearby shops
        nearby_shops = []
        shop_ids_within_radius = []
        for shop_id, shop_name, shop_lat, shop_lon in all_shops:
            shop_location = (shop_lat, shop_lon)
            distance = calculate_distance(user_location, shop_location)
            if distance <= radius_km:
                nearby_shops.append({
                    'shop_id': shop_id,
                    'shop_name': shop_name,
                    'latitude': shop_lat,
                    'longitude': shop_lon,
                    'distance': distance
                })
                shop_ids_within_radius.append(shop_id)

        if not nearby_shops:
            return {'type': 'no_shops', 'message': 'No shops found within the specified radius.'}

        # Step 4: Bulk Fetch Shop Inventories
        if not shop_ids_within_radius:
            return {'type': 'no_shops', 'message': 'No shops found within the specified radius.'}

        # Prepare placeholders for SQL IN clause
        placeholders = ','.join(['?'] * len(shop_ids_within_radius))
        query = f'''
            SELECT shop_id, ingredient_name, quantity, unit
            FROM ShopInventory
            WHERE shop_id IN ({placeholders})
        '''
        cursor_shops.execute(query, shop_ids_within_radius)
        shop_inventories = cursor_shops.fetchall()

        # Organize inventories by shop_id
        shop_inventory_map = {}
        for shop_id, ingredient_name, quantity, unit in shop_inventories:
            if shop_id not in shop_inventory_map:
                shop_inventory_map[shop_id] = {}
            shop_inventory_map[shop_id][ingredient_name] = {'quantity': quantity, 'unit': unit}

        # Step 5: Check for Single Shop Fulfillment
        single_shops = []
        for shop in nearby_shops:
            inventory = shop_inventory_map.get(shop['shop_id'], {})
            has_all = True
            for ingredient, details in ingredients_needed.items():
                item = inventory.get(ingredient)
                if not item:
                    has_all = False
                    break
                if item['unit'] != details['unit'] or item['quantity'] < details['quantity']:
                    has_all = False
                    break
            if has_all:
                single_shops.append(shop)

        if single_shops:
            return {
                'type': 'single',
                'shops': single_shops
            }

        # Step 6: Find Multiple Shops Fulfillment
        # Assign each ingredient to the closest shop that has it
        ingredient_to_shop = {}
        for ingredient, details in ingredients_needed.items():
            required_qty = details['quantity']
            required_unit = details['unit']
            # Find shops that have this ingredient in sufficient quantity and correct unit
            shops_with_ingredient = []
            for shop in nearby_shops:
                inventory = shop_inventory_map.get(shop['shop_id'], {})
                item = inventory.get(ingredient)
                if item and item['unit'] == required_unit and item['quantity'] >= required_qty:
                    shops_with_ingredient.append(shop)
            if not shops_with_ingredient:
                # Ingredient not available in any nearby shop
                return {
                    'type': 'unavailable',
                    'ingredient': ingredient
                }
            # Assign the closest shop
            closest_shop = min(shops_with_ingredient, key=lambda x: x['distance'])
            ingredient_to_shop[ingredient] = closest_shop

        # Collect unique shops from the assignments
        selected_shops = list({shop['shop_id']: shop for shop in ingredient_to_shop.values()}.values())

        # Sort shops by distance for optimized routing
        selected_shops.sort(key=lambda x: x['distance'])

        return {
            'type': 'multiple',
            'shops': selected_shops
        }

    except sqlite3.Error as db_error:
        # Log the error or handle it appropriately
        print(f"Database error: {db_error}")
        return {'type': 'error', 'message': 'An error occurred while accessing the database.'}
    except Exception as e:
        # Handle unexpected exceptions
        print(f"Unexpected error: {e}")
        return {'type': 'error', 'message': 'An unexpected error occurred.'}




# Function to generate Google Maps URL with optimized waypoints
def generate_google_maps_url(user_location, shops):
    """
    Generates a Google Maps URL for directions from the user's location
    to the list of shops in an optimized order.
    """
    base_url = "https://www.google.com/maps/dir/?api=1"
    origin = f"{user_location[0]},{user_location[1]}"

    if not shops:
        return base_url

    waypoints = "|".join([f"{shop['latitude']},{shop['longitude']}" for shop in shops])

    params = {
        'origin': origin,
        'travelmode': 'driving',
        'waypoints': f"optimize:true|{waypoints}"
    }

    url = f"{base_url}&{urlencode(params)}"
    return url


# Function to parse ingredient string
def parse_ingredient(ingredient_str):
    pattern = r'(?P<quantity>\d+(\.\d+)?)\s*(?P<unit>\w+)\s+(?:of\s+)?(?P<name>.+)'
    match = re.match(pattern, ingredient_str)
    if match:
        quantity = float(match.group('quantity'))
        unit = match.group('unit')
        name = match.group('name').strip()
        return {'quantity': quantity, 'unit': unit, 'name': name}
    else:
        # Handle cases without units or quantities
        return {'quantity': None, 'unit': None, 'name': ingredient_str.strip()}


def load_dataset(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
    return data['recipes']


def populate_recipes(recipes):
    for recipe in tqdm(recipes, desc="Populating Recipes"):
        recipe_name = recipe['title'].strip()
        ingredients = recipe['ingredients']

        # Add recipe to Recipes table
        try:
            cursor_recipes.execute('INSERT INTO Recipes (recipe_name) VALUES (?)', (recipe_name,))
            recipe_id = cursor_recipes.lastrowid
        except sqlite3.IntegrityError:
            print(f"Recipe '{recipe_name}' already exists. Skipping.")
            continue

        # Parse and add ingredients to RecipeIngredients table
        for ingredient_str in ingredients:
            parsed = parse_ingredient(ingredient_str)
            cursor_recipes.execute('''
                INSERT INTO RecipeIngredients (recipe_id, ingredient_name, quantity, unit)
                VALUES (?, ?, ?, ?)
            ''', (recipe_id, parsed['name'], parsed['quantity'], parsed['unit']))

    conn_recipes.commit()


# ---------------------------
# GUI Setup and Functions
# ---------------------------

# Initialize the main window
root = tk.Tk()
root.title("Recipe and Shop Manager")
root.geometry("800x700")

notebook = ttk.Notebook(root)
notebook.pack(expand=True, fill='both')

# ---------------------------
# Tab 1: Add Recipe
# ---------------------------
tab_add_recipe = ttk.Frame(notebook)
notebook.add(tab_add_recipe, text='Add Recipe')

# Recipe Name Entry
tk.Label(tab_add_recipe, text="Recipe Name:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
entry_recipe_name = tk.Entry(tab_add_recipe, width=50)
entry_recipe_name.grid(row=0, column=1, padx=5, pady=5)

# Ingredients Section
tk.Label(tab_add_recipe, text="Ingredients:").grid(row=1, column=0, padx=5, pady=5, sticky='ne')
frame_ingredients = tk.Frame(tab_add_recipe)
frame_ingredients.grid(row=1, column=1, padx=5, pady=5)

# Ingredient Name
tk.Label(frame_ingredients, text="Name").grid(row=0, column=0, padx=2, pady=2)
entry_ing_name = tk.Entry(frame_ingredients, width=20)
entry_ing_name.grid(row=0, column=1, padx=2, pady=2)

# Quantity
tk.Label(frame_ingredients, text="Quantity").grid(row=0, column=2, padx=2, pady=2)
entry_ing_qty = tk.Entry(frame_ingredients, width=10)
entry_ing_qty.grid(row=0, column=3, padx=2, pady=2)

# Unit
tk.Label(frame_ingredients, text="Unit").grid(row=0, column=4, padx=2, pady=2)
entry_ing_unit = tk.Entry(frame_ingredients, width=10)
entry_ing_unit.grid(row=0, column=5, padx=2, pady=2)


# Add Ingredient Button
def add_ingredient():
    name = entry_ing_name.get().strip()
    qty = entry_ing_qty.get().strip()
    unit = entry_ing_unit.get().strip()
    if not name or not qty or not unit:
        messagebox.showerror("Input Error", "Please fill in all ingredient fields.")
        return
    try:
        qty = float(qty)
        if qty <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Input Error", "Please enter a valid positive number for quantity.")
        return
    listbox_ingredients.insert(tk.END, f"{name}: {qty} {unit}")
    entry_ing_name.delete(0, tk.END)
    entry_ing_qty.delete(0, tk.END)
    entry_ing_unit.delete(0, tk.END)


btn_add_ingredient = tk.Button(frame_ingredients, text="Add Ingredient", command=add_ingredient)
btn_add_ingredient.grid(row=0, column=6, padx=5, pady=2)

# Ingredients Listbox
listbox_ingredients = tk.Listbox(tab_add_recipe, width=60, height=10)
listbox_ingredients.grid(row=2, column=1, padx=5, pady=5)


# Remove Ingredient Button
def remove_ingredient():
    selected = listbox_ingredients.curselection()
    if not selected:
        return
    listbox_ingredients.delete(selected[0])


btn_remove_ingredient = tk.Button(tab_add_recipe, text="Remove Selected Ingredient", command=remove_ingredient)
btn_remove_ingredient.grid(row=3, column=1, padx=5, pady=5, sticky='w')


# Add Recipe Button
def gui_add_recipe():
    recipe_name = entry_recipe_name.get().strip()
    if not recipe_name:
        messagebox.showerror("Input Error", "Recipe name cannot be empty.")
        return
    ingredients = []
    for i in range(listbox_ingredients.size()):
        item = listbox_ingredients.get(i)
        try:
            name_part, qty_unit_part = item.split(':', 1)
            qty, unit = qty_unit_part.strip().split(' ', 1)
            ingredients.append({
                'name': name_part.strip(),
                'quantity': float(qty),
                'unit': unit.strip()
            })
        except ValueError:
            messagebox.showerror("Format Error", f"Invalid ingredient format: '{item}'.")
            return
    if not ingredients:
        messagebox.showerror("Input Error", "Please add at least one ingredient.")
        return
    add_recipe(recipe_name, ingredients)
    messagebox.showinfo("Success", f"Recipe '{recipe_name}' added successfully.")
    # Clear inputs
    entry_recipe_name.delete(0, tk.END)
    listbox_ingredients.delete(0, tk.END)


btn_add_recipe = tk.Button(tab_add_recipe, text="Add Recipe", command=gui_add_recipe)
btn_add_recipe.grid(row=4, column=1, padx=5, pady=10, sticky='e')


# Import Recipe Dataset Button
def import_data():
    file_path = filedialog.askopenfilename(
        title="Select Recipe Dataset",
        filetypes=(("JSON Files", "*.json"), ("All Files", "*.*"))
    )
    if file_path:
        try:
            recipes = load_dataset(file_path)
            populate_recipes(recipes)
            messagebox.showinfo("Import Successful", "Recipes imported successfully!")
            load_recipes_in_combobox()
            load_manage_recipes()
        except Exception as e:
            messagebox.showerror("Import Failed", f"An error occurred during import: {e}")


btn_import_data = tk.Button(tab_add_recipe, text="Import Recipe Dataset", command=import_data)
btn_import_data.grid(row=5, column=1, padx=5, pady=10, sticky='e')

# ---------------------------
# Tab 2: Add Shop
# ---------------------------
tab_add_shop = ttk.Frame(notebook)
notebook.add(tab_add_shop, text='Add Shop')

# Shop Name Entry
tk.Label(tab_add_shop, text="Shop Name:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
entry_shop_name = tk.Entry(tab_add_shop, width=50)
entry_shop_name.grid(row=0, column=1, padx=5, pady=5)

# Latitude Entry
tk.Label(tab_add_shop, text="Latitude:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
entry_latitude = tk.Entry(tab_add_shop, width=50)
entry_latitude.grid(row=1, column=1, padx=5, pady=5)

# Longitude Entry
tk.Label(tab_add_shop, text="Longitude:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
entry_longitude = tk.Entry(tab_add_shop, width=50)
entry_longitude.grid(row=2, column=1, padx=5, pady=5)

# Inventory Section
tk.Label(tab_add_shop, text="Inventory:").grid(row=3, column=0, padx=5, pady=5, sticky='ne')
frame_inventory = tk.Frame(tab_add_shop)
frame_inventory.grid(row=3, column=1, padx=5, pady=5)

# Inventory Name
tk.Label(frame_inventory, text="Name").grid(row=0, column=0, padx=2, pady=2)
entry_inv_name = tk.Entry(frame_inventory, width=20)
entry_inv_name.grid(row=0, column=1, padx=2, pady=2)

# Quantity
tk.Label(frame_inventory, text="Quantity").grid(row=0, column=2, padx=2, pady=2)
entry_inv_qty = tk.Entry(frame_inventory, width=10)
entry_inv_qty.grid(row=0, column=3, padx=2, pady=2)

# Unit
tk.Label(frame_inventory, text="Unit").grid(row=0, column=4, padx=2, pady=2)
entry_inv_unit = tk.Entry(frame_inventory, width=10)
entry_inv_unit.grid(row=0, column=5, padx=2, pady=2)


# Add Inventory Item Button
def add_inventory_item():
    name = entry_inv_name.get().strip()
    qty = entry_inv_qty.get().strip()
    unit = entry_inv_unit.get().strip()
    if not name or not qty or not unit:
        messagebox.showerror("Input Error", "Please fill in all inventory fields.")
        return
    try:
        qty = float(qty)
        if qty <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Input Error", "Please enter a valid positive number for quantity.")
        return
    listbox_inventory.insert(tk.END, f"{name}: {qty} {unit}")
    entry_inv_name.delete(0, tk.END)
    entry_inv_qty.delete(0, tk.END)
    entry_inv_unit.delete(0, tk.END)


btn_add_inventory = tk.Button(frame_inventory, text="Add Item", command=add_inventory_item)
btn_add_inventory.grid(row=0, column=6, padx=5, pady=2)

# Inventory Listbox
listbox_inventory = tk.Listbox(tab_add_shop, width=60, height=10)
listbox_inventory.grid(row=4, column=1, padx=5, pady=5)


# Remove Inventory Item Button
def remove_inventory_item():
    selected = listbox_inventory.curselection()
    if not selected:
        return
    listbox_inventory.delete(selected[0])


btn_remove_inventory = tk.Button(tab_add_shop, text="Remove Selected Inventory", command=remove_inventory_item)
btn_remove_inventory.grid(row=5, column=1, padx=5, pady=5, sticky='w')


# Add Shop Button
def gui_add_shop():
    shop_name = entry_shop_name.get().strip()
    if not shop_name:
        messagebox.showerror("Input Error", "Shop name cannot be empty.")
        return
    try:
        latitude = float(entry_latitude.get())
        longitude = float(entry_longitude.get())
    except ValueError:
        messagebox.showerror("Input Error", "Please enter valid numerical values for latitude and longitude.")
        return
    inventory = []
    for i in range(listbox_inventory.size()):
        item = listbox_inventory.get(i)
        try:
            name_part, qty_unit_part = item.split(':', 1)
            qty, unit = qty_unit_part.strip().split(' ', 1)
            inventory.append({
                'name': name_part.strip(),
                'quantity': float(qty),
                'unit': unit.strip()
            })
        except ValueError:
            messagebox.showerror("Format Error", f"Invalid inventory format: '{item}'.")
            return
    if not inventory:
        messagebox.showerror("Input Error", "Please add at least one inventory item.")
        return
    add_shop(shop_name, latitude, longitude, inventory)
    messagebox.showinfo("Success", f"Shop '{shop_name}' added successfully.")
    # Clear inputs
    entry_shop_name.delete(0, tk.END)
    entry_latitude.delete(0, tk.END)
    entry_longitude.delete(0, tk.END)
    listbox_inventory.delete(0, tk.END)


btn_add_shop = tk.Button(tab_add_shop, text="Add Shop", command=gui_add_shop)
btn_add_shop.grid(row=6, column=1, padx=5, pady=10, sticky='e')

# ---------------------------
# Tab 3: Find Nearby Shops
# ---------------------------
tab_find_shops = ttk.Frame(notebook)
notebook.add(tab_find_shops, text='Find Nearby Shops')

# User Location Entries
tk.Label(tab_find_shops, text="Your Latitude:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
entry_user_latitude = tk.Entry(tab_find_shops, width=50)
entry_user_latitude.grid(row=0, column=1, padx=5, pady=5)

tk.Label(tab_find_shops, text="Your Longitude:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
entry_user_longitude = tk.Entry(tab_find_shops, width=50)
entry_user_longitude.grid(row=1, column=1, padx=5, pady=5)

# Recipe Selection with Combobox
tk.Label(tab_find_shops, text="Select Recipe:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
combo_recipes = ttk.Combobox(tab_find_shops, width=47, state='readonly')
combo_recipes.grid(row=2, column=1, padx=5, pady=5)
refresh_recipes = True  # Flag to refresh recipes list


def load_recipes_in_combobox():
    recipes = get_all_recipes()
    recipe_names = [f"{rid}: {rname}" for rid, rname in recipes]
    combo_recipes['values'] = recipe_names


load_recipes_in_combobox()

# Radius Entry
tk.Label(tab_find_shops, text="Search Radius (km):").grid(row=3, column=0, padx=5, pady=5, sticky='e')
entry_radius = tk.Entry(tab_find_shops, width=50)
entry_radius.grid(row=3, column=1, padx=5, pady=5)
entry_radius.insert(0, "10")  # Default radius


# Find Shops Button
def gui_find_shops():
    try:
        user_lat = float(entry_user_latitude.get())
        user_lon = float(entry_user_longitude.get())
        radius = float(entry_radius.get())
    except ValueError:
        messagebox.showerror("Input Error", "Please enter valid numerical values for location and radius.")
        return
    selected_recipe = combo_recipes.get()
    if not selected_recipe:
        messagebox.showerror("Input Error", "Please select a recipe.")
        return
    try:
        recipe_id = int(selected_recipe.split(':')[0])
    except ValueError:
        messagebox.showerror("Format Error", "Invalid recipe selection.")
        return
    result = find_nearby_shops_for_recipe(recipe_id, (user_lat, user_lon), radius)
    listbox_results.delete(0, tk.END)

    if result['type'] == 'single':
        listbox_results.insert(tk.END, "Single shops that have all ingredients:")
        for shop in result['shops']:
            # Retrieve shop name
            cursor_shops.execute('SELECT shop_name FROM Shops WHERE shop_id = ?', (shop['shop_id'],))
            shop_name = cursor_shops.fetchone()[0]
            listbox_results.insert(tk.END, f"Shop Name: {shop_name}, Distance: {shop['distance']:.2f} km")
        # Enable View Route button
        btn_view_route.config(state='normal')
        # Store selected shops
        tab_find_shops.selected_shops = result['shops']
    elif result['type'] == 'multiple':
        listbox_results.insert(tk.END, "Multiple shops required to cover all ingredients:")
        for shop in result['shops']:
            # Retrieve shop name
            cursor_shops.execute('SELECT shop_name FROM Shops WHERE shop_id = ?', (shop['shop_id'],))
            shop_name = cursor_shops.fetchone()[0]
            listbox_results.insert(tk.END, f"Shop Name: {shop_name}, Distance: {shop['distance']:.2f} km")
        # Enable View Route button
        btn_view_route.config(state='normal')
        # Store selected shops
        tab_find_shops.selected_shops = result['shops']
    elif result['type'] == 'unavailable':
        messagebox.showwarning("Unavailable Ingredient",
                               f"Ingredient '{result['ingredient']}' is not available in any nearby shop.")
        btn_view_route.config(state='disabled')
    else:
        messagebox.showinfo("No Shops Found", "No shops found within the specified radius.")
        btn_view_route.config(state='disabled')


btn_find_shops = tk.Button(tab_find_shops, text="Find Shops", command=gui_find_shops)
btn_find_shops.grid(row=4, column=1, padx=5, pady=5, sticky='e')

# Results Listbox
listbox_results = tk.Listbox(tab_find_shops, width=80, height=15)
listbox_results.grid(row=5, column=0, columnspan=2, padx=5, pady=5)


# View Route Button
def gui_view_route():
    if not hasattr(tab_find_shops, 'selected_shops') or not tab_find_shops.selected_shops:
        messagebox.showwarning("No Shops Selected", "No shops selected to view the route.")
        return
    try:
        user_lat = float(entry_user_latitude.get())
        user_lon = float(entry_user_longitude.get())
        user_location = (user_lat, user_lon)
    except ValueError:
        messagebox.showerror("Input Error", "Invalid user location coordinates.")
        return
    shops = tab_find_shops.selected_shops
    url = generate_google_maps_url(user_location, shops)
    webbrowser.open(url)


btn_view_route = tk.Button(tab_find_shops, text="View Optimized Route on Google Maps", command=gui_view_route,
                           state='disabled')
btn_view_route.grid(row=6, column=1, padx=5, pady=5, sticky='e')

# ---------------------------
# Tab 4: Manage Recipes
# ---------------------------
tab_manage_recipes = ttk.Frame(notebook)
notebook.add(tab_manage_recipes, text='Manage Recipes')

# Recipes Listbox
listbox_manage_recipes = tk.Listbox(tab_manage_recipes, width=80, height=20)
listbox_manage_recipes.grid(row=0, column=0, columnspan=3, padx=5, pady=5)


def load_manage_recipes():
    listbox_manage_recipes.delete(0, tk.END)
    recipes = get_all_recipes()
    for rid, rname in recipes:
        listbox_manage_recipes.insert(tk.END, f"{rid}: {rname}")


load_manage_recipes()


# Update Recipe Button
def gui_update_recipe():
    selected = listbox_manage_recipes.curselection()
    if not selected:
        messagebox.showerror("Selection Error", "Please select a recipe to update.")
        return
    recipe = listbox_manage_recipes.get(selected[0])
    try:
        recipe_id, recipe_name = recipe.split(':', 1)
        recipe_id = int(recipe_id.strip())
        recipe_name = recipe_name.strip()
    except ValueError:
        messagebox.showerror("Format Error", "Invalid recipe selection.")
        return
    # Open a new window to update recipe
    update_window = tk.Toplevel(root)
    update_window.title(f"Update Recipe: {recipe_name}")
    update_window.geometry("600x500")

    # Recipe Name Entry
    tk.Label(update_window, text="Recipe Name:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
    entry_update_recipe_name = tk.Entry(update_window, width=50)
    entry_update_recipe_name.grid(row=0, column=1, padx=5, pady=5)
    entry_update_recipe_name.insert(0, recipe_name)

    # Ingredients Section
    tk.Label(update_window, text="Ingredients:").grid(row=1, column=0, padx=5, pady=5, sticky='ne')
    frame_update_ingredients = tk.Frame(update_window)
    frame_update_ingredients.grid(row=1, column=1, padx=5, pady=5)

    # Ingredient Name
    tk.Label(frame_update_ingredients, text="Name").grid(row=0, column=0, padx=2, pady=2)
    entry_update_ing_name = tk.Entry(frame_update_ingredients, width=20)
    entry_update_ing_name.grid(row=0, column=1, padx=2, pady=2)

    # Quantity
    tk.Label(frame_update_ingredients, text="Quantity").grid(row=0, column=2, padx=2, pady=2)
    entry_update_ing_qty = tk.Entry(frame_update_ingredients, width=10)
    entry_update_ing_qty.grid(row=0, column=3, padx=2, pady=2)

    # Unit
    tk.Label(frame_update_ingredients, text="Unit").grid(row=0, column=4, padx=2, pady=2)
    entry_update_ing_unit = tk.Entry(frame_update_ingredients, width=10)
    entry_update_ing_unit.grid(row=0, column=5, padx=2, pady=2)

    # Add Ingredient Button
    def add_update_ingredient():
        name = entry_update_ing_name.get().strip()
        qty = entry_update_ing_qty.get().strip()
        unit = entry_update_ing_unit.get().strip()
        if not name or not qty or not unit:
            messagebox.showerror("Input Error", "Please fill in all ingredient fields.")
            return
        try:
            qty = float(qty)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Input Error", "Please enter a valid positive number for quantity.")
            return
        listbox_update_ingredients.insert(tk.END, f"{name}: {qty} {unit}")
        entry_update_ing_name.delete(0, tk.END)
        entry_update_ing_qty.delete(0, tk.END)
        entry_update_ing_unit.delete(0, tk.END)

    btn_add_update_ingredient = tk.Button(frame_update_ingredients, text="Add Ingredient",
                                          command=add_update_ingredient)
    btn_add_update_ingredient.grid(row=0, column=6, padx=5, pady=2)

    # Ingredients Listbox
    listbox_update_ingredients = tk.Listbox(update_window, width=60, height=10)
    listbox_update_ingredients.grid(row=2, column=1, padx=5, pady=5)

    # Load existing ingredients
    cursor_recipes.execute('''
    SELECT ingredient_name, quantity, unit FROM RecipeIngredients WHERE recipe_id = ?
    ''', (recipe_id,))
    ingredients = cursor_recipes.fetchall()
    for name, qty, unit in ingredients:
        listbox_update_ingredients.insert(tk.END, f"{name}: {qty} {unit}")

    # Remove Ingredient Button
    def remove_update_ingredient():
        selected = listbox_update_ingredients.curselection()
        if not selected:
            return
        listbox_update_ingredients.delete(selected[0])

    btn_remove_update_ingredient = tk.Button(update_window, text="Remove Selected Ingredient",
                                             command=remove_update_ingredient)
    btn_remove_update_ingredient.grid(row=3, column=1, padx=5, pady=5, sticky='w')

    # Update Recipe Function
    def submit_update_recipe():
        new_name = entry_update_recipe_name.get().strip()
        if not new_name:
            messagebox.showerror("Input Error", "Recipe name cannot be empty.")
            return
        new_ingredients = []
        for i in range(listbox_update_ingredients.size()):
            item = listbox_update_ingredients.get(i)
            try:
                name_part, qty_unit_part = item.split(':', 1)
                qty, unit = qty_unit_part.strip().split(' ', 1)
                new_ingredients.append({
                    'name': name_part.strip(),
                    'quantity': float(qty),
                    'unit': unit.strip()
                })
            except ValueError:
                messagebox.showerror("Format Error", f"Invalid ingredient format: '{item}'.")
                return
        if not new_ingredients:
            messagebox.showerror("Input Error", "Please add at least one ingredient.")
            return
        update_recipe(recipe_id, new_name, new_ingredients)
        messagebox.showinfo("Success", f"Recipe '{new_name}' updated successfully.")
        update_window.destroy()
        load_manage_recipes()

    # Update Recipe Button
    btn_submit_update = tk.Button(update_window, text="Update Recipe", command=submit_update_recipe)
    btn_submit_update.grid(row=4, column=1, padx=5, pady=10, sticky='e')


# Delete Recipe Button
def gui_delete_recipe():
    selected = listbox_manage_recipes.curselection()
    if not selected:
        messagebox.showerror("Selection Error", "Please select a recipe to delete.")
        return
    recipe = listbox_manage_recipes.get(selected[0])
    try:
        recipe_id, recipe_name = recipe.split(':', 1)
        recipe_id = int(recipe_id.strip())
        recipe_name = recipe_name.strip()
    except ValueError:
        messagebox.showerror("Format Error", "Invalid recipe selection.")
        return
    confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete recipe '{recipe_name}'?")
    if confirm:
        delete_recipe(recipe_id)
        messagebox.showinfo("Success", f"Recipe '{recipe_name}' deleted successfully.")
        load_manage_recipes()


btn_update_recipe = tk.Button(tab_manage_recipes, text="Update Selected Recipe", command=gui_update_recipe)
btn_update_recipe.grid(row=1, column=0, padx=5, pady=5, sticky='w')

btn_delete_recipe = tk.Button(tab_manage_recipes, text="Delete Selected Recipe", command=gui_delete_recipe)
btn_delete_recipe.grid(row=1, column=1, padx=5, pady=5, sticky='w')


# Refresh Recipes Button
def refresh_recipes_list():
    load_recipes_in_combobox()
    load_manage_recipes()


btn_refresh_recipes = tk.Button(tab_manage_recipes, text="Refresh Recipe List", command=refresh_recipes_list)
btn_refresh_recipes.grid(row=1, column=2, padx=5, pady=5, sticky='e')

# ---------------------------
# Tab 5: Manage Shops
# ---------------------------
tab_manage_shops = ttk.Frame(notebook)
notebook.add(tab_manage_shops, text='Manage Shops')

# Shops Listbox
listbox_manage_shops = tk.Listbox(tab_manage_shops, width=80, height=20)
listbox_manage_shops.grid(row=0, column=0, columnspan=3, padx=5, pady=5)


def load_manage_shops():
    listbox_manage_shops.delete(0, tk.END)
    shops = get_all_shops()
    for sid, sname in shops:
        listbox_manage_shops.insert(tk.END, f"{sid}: {sname}")


load_manage_shops()


# Update Shop Button
def gui_update_shop():
    selected = listbox_manage_shops.curselection()
    if not selected:
        messagebox.showerror("Selection Error", "Please select a shop to update.")
        return
    shop = listbox_manage_shops.get(selected[0])
    try:
        shop_id, shop_name = shop.split(':', 1)
        shop_id = shop_id.strip()
        shop_name = shop_name.strip()
    except ValueError:
        messagebox.showerror("Format Error", "Invalid shop selection.")
        return
    # Open a new window to update shop
    update_window = tk.Toplevel(root)
    update_window.title(f"Update Shop: {shop_name}")
    update_window.geometry("700x600")

    # Shop Name Entry
    tk.Label(update_window, text="Shop Name:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
    entry_update_shop_name = tk.Entry(update_window, width=50)
    entry_update_shop_name.grid(row=0, column=1, padx=5, pady=5)
    entry_update_shop_name.insert(0, shop_name)

    # Latitude Entry
    tk.Label(update_window, text="Latitude:").grid(row=1, column=0, padx=5, pady=5, sticky='e')
    entry_update_latitude = tk.Entry(update_window, width=50)
    entry_update_latitude.grid(row=1, column=1, padx=5, pady=5)

    # Longitude Entry
    tk.Label(update_window, text="Longitude:").grid(row=2, column=0, padx=5, pady=5, sticky='e')
    entry_update_longitude = tk.Entry(update_window, width=50)
    entry_update_longitude.grid(row=2, column=1, padx=5, pady=5)

    # Load existing latitude and longitude
    cursor_shops.execute('SELECT latitude, longitude FROM Shops WHERE shop_id = ?', (shop_id,))
    lat, lon = cursor_shops.fetchone()
    entry_update_latitude.insert(0, str(lat))
    entry_update_longitude.insert(0, str(lon))

    # Inventory Section
    tk.Label(update_window, text="Inventory:").grid(row=3, column=0, padx=5, pady=5, sticky='ne')
    frame_update_inventory = tk.Frame(update_window)
    frame_update_inventory.grid(row=3, column=1, padx=5, pady=5)

    # Inventory Name
    tk.Label(frame_update_inventory, text="Name").grid(row=0, column=0, padx=2, pady=2)
    entry_update_inv_name = tk.Entry(frame_update_inventory, width=20)
    entry_update_inv_name.grid(row=0, column=1, padx=2, pady=2)

    # Quantity
    tk.Label(frame_update_inventory, text="Quantity").grid(row=0, column=2, padx=2, pady=2)
    entry_update_inv_qty = tk.Entry(frame_update_inventory, width=10)
    entry_update_inv_qty.grid(row=0, column=3, padx=2, pady=2)

    # Unit
    tk.Label(frame_update_inventory, text="Unit").grid(row=0, column=4, padx=2, pady=2)
    entry_update_inv_unit = tk.Entry(frame_update_inventory, width=10)
    entry_update_inv_unit.grid(row=0, column=5, padx=2, pady=2)

    # Add Inventory Item Button
    def add_update_inventory_item():
        name = entry_update_inv_name.get().strip()
        qty = entry_update_inv_qty.get().strip()
        unit = entry_update_inv_unit.get().strip()
        if not name or not qty or not unit:
            messagebox.showerror("Input Error", "Please fill in all inventory fields.")
            return
        try:
            qty = float(qty)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Input Error", "Please enter a valid positive number for quantity.")
            return
        listbox_update_inventory.insert(tk.END, f"{name}: {qty} {unit}")
        entry_update_inv_name.delete(0, tk.END)
        entry_update_inv_qty.delete(0, tk.END)
        entry_update_inv_unit.delete(0, tk.END)

    btn_add_update_inventory = tk.Button(frame_update_inventory, text="Add Item", command=add_update_inventory_item)
    btn_add_update_inventory.grid(row=0, column=6, padx=5, pady=2)

    # Inventory Listbox
    listbox_update_inventory = tk.Listbox(update_window, width=60, height=10)
    listbox_update_inventory.grid(row=4, column=1, padx=5, pady=5)

    # Load existing inventory
    cursor_shops.execute('''
    SELECT ingredient_name, quantity, unit FROM ShopInventory WHERE shop_id = ?
    ''', (shop_id,))
    inventory = cursor_shops.fetchall()
    for name, qty, unit in inventory:
        listbox_update_inventory.insert(tk.END, f"{name}: {qty} {unit}")

    # Remove Inventory Item Button
    def remove_update_inventory_item():
        selected = listbox_update_inventory.curselection()
        if not selected:
            return
        listbox_update_inventory.delete(selected[0])

    btn_remove_update_inventory = tk.Button(update_window, text="Remove Selected Inventory",
                                            command=remove_update_inventory_item)
    btn_remove_update_inventory.grid(row=5, column=1, padx=5, pady=5, sticky='w')

    # Update Shop Function
    def submit_update_shop():
        new_name = entry_update_shop_name.get().strip()
        if not new_name:
            messagebox.showerror("Input Error", "Shop name cannot be empty.")
            return
        try:
            new_lat = float(entry_update_latitude.get())
            new_lon = float(entry_update_longitude.get())
        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid numerical values for latitude and longitude.")
            return
        new_inventory = []
        for i in range(listbox_update_inventory.size()):
            item = listbox_update_inventory.get(i)
            try:
                name_part, qty_unit_part = item.split(':', 1)
                qty, unit = qty_unit_part.strip().split(' ', 1)
                new_inventory.append({
                    'name': name_part.strip(),
                    'quantity': float(qty),
                    'unit': unit.strip()
                })
            except ValueError:
                messagebox.showerror("Format Error", f"Invalid inventory format: '{item}'.")
                return
        if not new_inventory:
            messagebox.showerror("Input Error", "Please add at least one inventory item.")
            return
        update_shop(shop_id, new_name, new_lat, new_lon, new_inventory)
        messagebox.showinfo("Success", f"Shop '{new_name}' updated successfully.")
        update_window.destroy()
        load_manage_shops()

    # Update Shop Button
    btn_submit_update_shop = tk.Button(update_window, text="Update Shop", command=submit_update_shop)
    btn_submit_update_shop.grid(row=6, column=1, padx=5, pady=10, sticky='e')


# Delete Shop Button
def gui_delete_shop():
    selected = listbox_manage_shops.curselection()
    if not selected:
        messagebox.showerror("Selection Error", "Please select a shop to delete.")
        return
    shop = listbox_manage_shops.get(selected[0])
    try:
        shop_id, shop_name = shop.split(':', 1)
        shop_id = shop_id.strip()
        shop_name = shop_name.strip()
    except ValueError:
        messagebox.showerror("Format Error", "Invalid shop selection.")
        return
    confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete shop '{shop_name}'?")
    if confirm:
        delete_shop(shop_id)
        messagebox.showinfo("Success", f"Shop '{shop_name}' deleted successfully.")
        load_manage_shops()


btn_update_shop = tk.Button(tab_manage_shops, text="Update Selected Shop", command=gui_update_shop)
btn_update_shop.grid(row=1, column=0, padx=5, pady=5, sticky='w')

btn_delete_shop = tk.Button(tab_manage_shops, text="Delete Selected Shop", command=gui_delete_shop)
btn_delete_shop.grid(row=1, column=1, padx=5, pady=5, sticky='w')


# Refresh Shops Button
def refresh_shops_list():
    load_manage_shops()


btn_refresh_shops = tk.Button(tab_manage_shops, text="Refresh Shop List", command=refresh_shops_list)
btn_refresh_shops.grid(row=1, column=2, padx=5, pady=5, sticky='e')


# ---------------------------
# Auto Import Function (Optional)
# ---------------------------

def auto_import():
    dataset_file = 'recipe-dataset/recipes.json'  # Ensure the path is correct
    try:
        recipes = load_dataset(dataset_file)
        populate_recipes(recipes)
        print("Auto-import successful.")
    except Exception as e:
        print(f"Auto-import failed: {e}")


# Uncomment the following line to enable auto-import on startup
# auto_import()

# ---------------------------
# Main Application Loop
# ---------------------------

root.mainloop()

# Close database connections when the GUI is closed
conn_recipes.close()
conn_shops.close()
