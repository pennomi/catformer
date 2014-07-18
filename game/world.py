"""The primary game object lives in this module."""
import pygame
from xml.etree import ElementTree
from pygame.color import THECOLORS
from pymunk import Vec2d
import pymunk
from pymunk.pygame_util import to_pygame
from game import SCREEN_HALF, JUMP_THROUGH_COLLISION_TYPE, SPACE


class Tileset(object):
    def __init__(self, filename):
        self.img = pygame.image.load(filename)
        self.tile_width = 32
        self.tile_height = 32

    def draw(self, screen, tile_id, position):
        if not tile_id:
            return  # There was nothing to be drawn
        tile_id -= 1  # we're 1-indexed in Tiled
        tiles_wide = self.img.get_width() // self.tile_width
        source_x = (tile_id % tiles_wide) * self.tile_width
        source_y = (tile_id // tiles_wide) * self.tile_height
        screen.blit(self.img, to_pygame(position, screen),
                    (source_x, source_y, self.tile_width, self.tile_height))


class TileWorld(object):
    def __init__(self, filename):
        # Somebody set up us the camera
        self.camera = Vec2d(0, 0)

        # Load the Tileset
        # TODO: tileset is hardcoded
        self.tileset = Tileset('res/images/mininicular.png')

        # Parse the TMX
        self.tree = ElementTree.parse(filename)
        root = self.tree.getroot()
        dim = Vec2d(int(root.get('width')), int(root.get('height')))
        t_size = Vec2d(int(root.get('tilewidth')), int(root.get('tileheight')))
        self.map_size = Vec2d(t_size.x*dim.x, t_size.y*dim.y)
        layers = []
        for layer in root.findall('layer'):
            # This is the csv of the map data
            csv = layer.findall('data')[0].text
            # pygame is opposite of Tiled, so needs reversed
            new_layer = list(reversed([row for row in csv.split('\n')]))
            layers.append(new_layer)

        # These are the collision objects
        self.platforms = []
        for object_group in root.findall('objectgroup'):
            for obj in object_group.iter('object'):
                jump_through = False
                speed = 1
                waypoints = []
                group_offset = Vec2d(int(obj.get('x')), int(obj.get('y')))
                for p in obj.iter('property'):
                    if p.get('name') == "jump_through":
                        jump_through = True
                    if p.get('name') == "speed":
                        speed = int(p.get('value'))
                    if p.get('name') == "waypoints":
                        waypoints = self.pointify(p.get('value'))
                line = obj.find('polyline')
                points = self.pointify(line.get('points'),
                                       group_offset=group_offset)
                p = Platform(points, jump_through=jump_through, speed=speed,
                             waypoints=waypoints)
                self.platforms.append(p)

        # Pre-generate the surfaces
        self.surfaces = []
        for layer in layers:
            surf = pygame.Surface(self.map_size, pygame.SRCALPHA, 32)
            self.generate_surface(surf, layer)
            self.surfaces.append(surf)

    def pointify(self, csv_string, group_offset=Vec2d.zero()):
        if group_offset.y:
            offset = self.map_size.y - group_offset.y
        else:
            offset = 0
        point_strings = [p.split(',') for p in csv_string.split()]
        return [(group_offset.x + int(p[0]),
                 offset-int(p[1])) for p in point_strings]

    def update(self, dt, players):
        # TODO: damage players outside of the map

        for p in self.platforms:
            p.update(dt, players)

        # Make the camera follow the center of the players
        living_players = [p for p in players if p.health > 0]
        count = len(living_players)
        if not count:
            return
        position = sum(p.feet.body.position for p in living_players) / count
        distance = self.camera.get_distance(position)
        camera_speed = max(distance**.5 / 3, .01)
        self.camera = self.camera.interpolate_to(position, camera_speed / distance)

    def generate_surface(self, surf, data):
        surf.convert_alpha()
        for y in range(len(data)):
            row = data[y].split(',')
            for x in range(len(row)):
                tile_id = row[x]
                if tile_id == '':
                    continue
                pos = Vec2d(x*32, y*32)
                self.tileset.draw(surf, int(tile_id), pos)

    def draw(self, screen):
        position = Vec2d(self.camera.x, 50*32-self.camera.y) - SCREEN_HALF
        count = len(self.surfaces) - 1.

        for i, surf in enumerate(self.surfaces):
            parallax_factor = i / count

            # constrain to the top and left
            temp = position * parallax_factor
            offset = position * (1 - parallax_factor)

            # constrain to the bottom and right
            size_offset = -position + self.map_size

            # Get the part of the surface to blit
            p = (-offset.x if offset.x < 0 else temp.x,
                 -offset.y if offset.y < 0 else temp.y,
                 size_offset.x, size_offset.y)
            screen.blit(surf, (-position.x if offset.x < 0 else 0,
                               -position.y if offset.y < 0 else 0), p)


class Platform(object):
    def __init__(self, points, jump_through=False, waypoints=None, speed=1):
        self.waypoints = waypoints
        self.speed = speed
        self.target_index = 0
        is_moving = bool(self.waypoints)

        # Create the body type
        if is_moving:
            self.body = pymunk.Body(pymunk.inf, pymunk.inf)
        else:
            self.body = SPACE.static_body

        for i in range(len(points)-1):
            # Make and configure the physics object
            seg = pymunk.Segment(self.body, points[i], points[i+1], 5)
            seg.friction = 1
            seg.group = 1
            if jump_through:
                seg.collision_type = JUMP_THROUGH_COLLISION_TYPE
                seg.color = (255, 255, 0, 255)
            if is_moving:
                seg.color = THECOLORS["blue"]
                seg.body.position = Vec2d(self.waypoints[0])
            # Add it to the world
            SPACE.add(seg)

    def update(self, dt, players):
        if not self.waypoints:
            return  # non-moving platforms don't matter
        destination = self.waypoints[self.target_index]
        current_pos = Vec2d(self.body.position)
        distance = current_pos.get_distance(destination)
        if distance < self.speed:
            self.target_index = (self.target_index + 1) % len(self.waypoints)
            t = 1
        else:
            t = self.speed / distance
        new_pos = current_pos.interpolate_to(destination, t)
        self.body.position = new_pos
        self.body.velocity = (new_pos - current_pos) / dt
