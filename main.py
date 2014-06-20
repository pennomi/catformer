"""Reworked platformer demo for pygame/pymunk.

Art from the good people at OpenGameArt.org

Cat Fighter sprites by dogchicken
http://opengameart.org/content/cat-fighter-sprite-sheet

Minimalist Tileset by Blarget2
http://opengameart.org/content/minimalist-pixel-tileset

Music by deadEarth
http://opengameart.org/content/a-fight
"""

# TODO ROADMAP:
# * Camera
# * Shooting stuff and death
# * Parallax

from xml.etree import ElementTree

import pygame
from pygame import locals as KEYS
from pygame.color import THECOLORS

import pymunk
from pymunk.vec2d import Vec2d
from pymunk.pygame_util import to_pygame


# Begin by initializing some constants for the physics world
PLAYER_COLLISION_TYPE = 1
JUMP_THROUGH_COLLISION_TYPE = 2
BULLET_COLLISION_TYPE = 3


def jump_through_collision_handler(space, arbiter):
    # pass through only if going up
    return arbiter.shapes[0].body.velocity.y < 0

SPACE = pymunk.Space()
SPACE.gravity = (0, -1000)  # in px/sec^2
SPACE.add_collision_handler(
    PLAYER_COLLISION_TYPE, JUMP_THROUGH_COLLISION_TYPE,
    begin=jump_through_collision_handler)
SPACE.add_collision_handler(
    PLAYER_COLLISION_TYPE, JUMP_THROUGH_COLLISION_TYPE,
    begin=jump_through_collision_handler)


def bullet_velocity_func(body, gravity, damping, dt):
    return body.velocity


class Bullet(object):
    def __init__(self, owner, gravity=False):
        self.radius = 3
        self.speed = 500
        self.ttl = 40
        self.cooldown = 10

        self.shot_sound = pygame.mixer.Sound("C_28P.ogg")
        self.shot_sound.play()

        facing_left = owner.current_facing == owner.left_key
        vel = Vec2d(-self.speed, 0) if facing_left else Vec2d(self.speed, 0)
        offset = Vec2d(0, 0) if facing_left else Vec2d(20, 0)
        self.body = pymunk.Body(1, pymunk.inf)
        self.body.position = owner.body.position + offset
        self.body.velocity = owner.body.velocity + vel
        if not gravity:
            self.body.velocity_func = bullet_velocity_func
        self.shape = pymunk.Circle(self.body, self.radius, (0, 0))
        self.shape.collision_type = BULLET_COLLISION_TYPE
        self.shape.friction = 0
        SPACE.add(self.body, self.shape)

    def update(self):
        self.ttl -= 1
        if self.ttl < 0:
            SPACE.remove(self.body, self.shape)
            return False
        return True

    def draw(self, screen):
        pygame.draw.circle(screen, (0, 0, 0, 0),
                           to_pygame(self.body.position, screen), self.radius)


class Animation(object):
    def __init__(self, images, row, frame_count,
                 start_frame=0, loop=False, frame_rate=.15):
        self.img, self.flip_img = images
        self.row = row
        self.frame_count = frame_count
        self.start_frame = start_frame
        self.loop = loop
        self.frame_rate = frame_rate
        self.current_frame = 0
        self.done = False

    def draw(self, screen, pos, flip):
        frame = int(self.current_frame)
        self.current_frame += self.frame_rate
        if self.current_frame >= self.frame_count:
            if self.loop:
                self.current_frame = 0
            else:
                self.current_frame -= self.frame_rate  # stick on the last frame
                self.done = True

        img = self.flip_img if flip else self.img
        # TODO: remove hardcoded sprite size
        sprite_size = 128
        x = (frame + self.start_frame) * sprite_size
        if flip:
            x = img.get_width() - x - sprite_size
        y = self.row * sprite_size
        screen.blit(img, to_pygame(pos, screen),
                    (x, y, sprite_size, sprite_size))


class Player(object):
    def __init__(self, name, img, up=KEYS.K_UP, left=KEYS.K_LEFT,
                 right=KEYS.K_RIGHT, down=KEYS.K_DOWN, shoot=KEYS.K_SPACE):
        self.name = name

        # sprites
        img = pygame.image.load(img)
        flip_img = pygame.transform.flip(img, True, False)
        images = (img, flip_img)

        # animations
        self.idle_loop = Animation(images, 0, 4, loop=True)
        self.walk_loop = Animation(images, 1, 8, loop=True)
        self.jump_loop = Animation(images, 2, 2, start_frame=2, loop=True)
        self.spin_loop = Animation(
            images, 3, 4, start_frame=3, loop=True, frame_rate=0.4)
        self.death_sequence = Animation(images, 4, 7)

        # sounds
        self.fall_sound = pygame.mixer.Sound("footstep05.ogg")

        # keybindings
        self.jump_key = up
        self.left_key = left
        self.right_key = right
        self.down_key = down
        self.shoot_key = shoot

        # physics
        self.body = pymunk.Body(5, pymunk.inf)  # mass, moment
        self.body.position = 100, 100

        # TODO: heads should be a separate collision type
        self.head = pymunk.Circle(self.body, 14, (12, 7))
        self.head.collision_type = PLAYER_COLLISION_TYPE
        self.head.friction = 0

        self.feet = pymunk.Circle(self.body, 14, (12, -16))
        self.feet.collision_type = 1
        # TODO: Make this zero whilst falling
        self.feet.friction = 2

        SPACE.add(self.body, self.head, self.feet)

        # Character stats
        self.max_jumps = 2
        self.remaining_jumps = self.max_jumps
        self.speed = 100
        self.jump_speed = 400
        self.max_health = 3
        self.health = self.max_health  # TODO: property with set/getters
        self.shot_cooldown = 0

        # State tracking
        self.landed = False
        self.landed_hard = False
        self.ground_velocity = Vec2d.zero()
        self.ground_slope = 0
        self.current_facing = self.right_key
        self.bullets = []

    def update(self, pressed_keys):
        for b in self.bullets[:]:  # iterate over a copy
            if not b.update():
                self.bullets.remove(b)

        # Tick the cooldown
        if self.shot_cooldown:
            self.shot_cooldown -= 1
        self.landed = False
        self.landed_hard = False

        def calculate_landing(arbiter):
            n = -arbiter.contacts[0].normal
            shape = arbiter.shapes[1]
            if n.y > 0 and shape.collision_type != BULLET_COLLISION_TYPE:
                # only one of these ever gets this far
                # wrap in Vec2d to copy the vector
                v = Vec2d(shape.body.velocity)
                self.ground_velocity = v
                self.landed = True
                # 100 is landed, 1000 is "being squished"
                landing_speed = arbiter.total_impulse.y / self.body.mass
                self.landed_hard = landing_speed > 100
                if landing_speed > 1000:
                    self.health -= 1
                self.ground_slope = n.x / n.y
        self.body.each_arbiter(calculate_landing)

        if self.health < 0:
            return  # No moving around for you!

        if self.landed and self.ground_slope < 2:
            self.remaining_jumps = self.max_jumps

        # Jump
        if pressed_keys.get(self.jump_key) == 1:
            self.jump()

        # Move
        self.move(pressed_keys)

        if pressed_keys.get(self.shoot_key):
            self.shoot()

    def shoot(self):
        if self.shot_cooldown:
            return
        bullet = Bullet(self)
        self.bullets.append(bullet)
        self.shot_cooldown = bullet.cooldown

    def jump(self):
        if self.remaining_jumps:
            self.body.velocity.y = self.ground_velocity.y + self.jump_speed
            self.remaining_jumps -= 1

    def draw(self, screen):
        # match sprite to the physics object
        position = self.body.position + (-48, 76)

        # play different animations depending on what's going on
        # TODO: These are all screwed up
        flip = self.current_facing == self.left_key

        if self.health < 0:
            self.death_sequence.draw(screen, position, flip)
        elif self.landed and abs(self.feet.surface_velocity.x) > 1:
            # walking
            self.walk_loop.draw(screen, position, flip)
        elif self.landed:
            # idle
            self.idle_loop.draw(screen, position, flip)
        elif self.remaining_jumps > 0:
            # falling
            self.jump_loop.draw(screen, position, flip)
        elif self.remaining_jumps == 0:
            # spinning
            self.spin_loop.draw(screen, position, flip)
        else:
            # I dunno what else to do
            self.idle_loop.draw(screen, position, flip)

        # Did we land?
        if self.landed_hard:
            self.fall_sound.play()

        # Draw our bullets
        for bullet in self.bullets:
            bullet.draw(screen)

    def move(self, keys):
        target_vx = 0
        if keys.get(self.left_key):
            self.current_facing = self.left_key
            target_vx = -self.speed
        if keys.get(self.right_key):
            self.current_facing = self.right_key
            target_vx = self.speed
        self.feet.surface_velocity = (target_vx, 0)

        # Smooth Air control
        def lerp(f1, f2, d):
            """Interpolate from f1 to f2 by no more than d."""
            return f1 + min(max(f2 - f1, -d), d)

        if not self.landed:
            self.body.velocity.x = lerp(
                self.body.velocity.x, target_vx + self.ground_velocity.x, 10)

        # Terminal velocity
        self.body.velocity.y = max(self.body.velocity.y, -300)


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
        # TODO: this class owns the camera and probably the players

        # Load the Tileset
        self.tileset = Tileset('mininicular.png')

        # Parse the TMX
        self.tree = ElementTree.parse(filename)
        root = self.tree.getroot()
        for layer in root.findall('layer'):
            # This is the csv of the map data
            csv = layer.findall('data')[0].text
            self.data = [row for row in csv.split('\n')]
            self.data.reverse()  # pygame is opposite of Tiled
        self.map_height = 32 * 50  # TODO: hardcoded

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

    def pointify(self, csv_string, group_offset=Vec2d.zero()):
        if group_offset.y:
            offset = self.map_height - group_offset.y
        else:
            offset = 0
        point_strings = [p.split(',') for p in csv_string.split()]
        return [(group_offset.x + int(p[0]),
                 offset-int(p[1])) for p in point_strings]

    def update(self, dt, players):
        for p in self.platforms:
            p.update(dt, players)

    def draw(self, screen):
        screen_h = screen.get_height() + 32
        screen_w = screen.get_width() + 32
        # TODO: only iterate over what'll fit on the screen
        # (We'll implement this *after* the camera)
        for y, row in enumerate(self.data):
            for x, tile_id in enumerate(row.split(',')):
                if tile_id == '':
                    continue
                if x*32 > screen_w:
                    continue
                if y*32 > screen_h:
                    continue
                self.tileset.draw(screen, int(tile_id), (x*32, y*32))


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

        for i in xrange(len(points)-1):
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

        # Follow the average position of the players
        # Not useful here, but potentially useful for camera
        #position = Vec2d(0, 0)
        #for player in players:
        #    position += player.feet.body.position
        #position /= len(players)
        #destination = position

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


def main():
    fps = 60
    dt = 1. / fps
    debug = False

    # Initialize the game
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=1, buffer=512)
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()
    running = True
    font = pygame.font.SysFont("Arial", 16)

    # Music!
    pygame.mixer.music.load("fight.mp3")
    pygame.mixer.music.play(-1)  # loop forever

    # Load the world
    world = TileWorld('level.tmx')

    # player
    player1 = Player("Player1", "cat1.png",
                     up=KEYS.K_UP, left=KEYS.K_LEFT,
                     right=KEYS.K_RIGHT, down=KEYS.K_DOWN, shoot=KEYS.K_SPACE)
    player2 = Player("Player2", "cat1.png",
                     up=KEYS.K_w, left=KEYS.K_a,
                     right=KEYS.K_d, down=KEYS.K_s, shoot=KEYS.K_e)
    players = [player1, player2]

    # track how long each key has been pressed
    pressed_keys = {}

    # Start the game loop
    while running:
        # Input management
        # Manage all events
        events = pygame.event.get()
        for event in events:
            pressed_window_x = event.type == KEYS.QUIT
            pressed_esc = (event.type == KEYS.KEYDOWN and
                           event.key in [KEYS.K_ESCAPE])
            pressed_q = (event.type == KEYS.KEYDOWN and
                         event.key in [KEYS.K_q])
            if pressed_window_x or pressed_esc:
                running = False  # exit the program
            if pressed_q:
                debug = not debug  # toggle debug drawing
        pressed = pygame.key.get_pressed()
        # increment all pressed keys
        for i, k in enumerate(pressed):
            if k:
                pressed_keys[i] = pressed_keys.get(i, 0) + 1
        # clear out any keys that are no longer pressed
        for k in pressed_keys.keys():
            if not pressed[k]:
                del pressed_keys[k]

        # Update physics
        SPACE.step(dt)

        # Update players
        for player in players:
            player.update(pressed_keys)

        # Move any moving platforms
        world.update(dt, players)

        # Draw stuff
        # Clear screen
        screen.fill((128, 125, 55, 255))  # Light green color
        # Draw tiles
        world.draw(screen)
        # Draw players
        for player in players:
            player.draw(screen)
        # Debug draw physics
        if debug:
            # TODO: Make this work with the camera
            pymunk.pygame_util.draw(screen, SPACE)
        # Draw fps label
        screen.blit(font.render("{} FPS".format(clock.get_fps()), 1,
                                THECOLORS["white"]), (0, 0))
        # Apply the drawing to the screen
        pygame.display.flip()

        # Wait for next frame
        clock.tick(fps)


if __name__ == '__main__':
    main()