import datetime
import logging
import matplotlib.pyplot as plt
import numpy as np

from opensfm import types
from opensfm import csfm
from opensfm.reconstruction import Chronometer
from opensfm import reconstruction
from opensfm import features
from opensfm import feature_loader

# from opensfm import plot_inliers

from slam_matcher import SlamMatcher
from slam_mapper import SlamMapper
from slam_frame import Frame
# import cv2
def plot_matches(im1, im2, p1, p2):
    h1, w1, c = im1.shape
    h2, w2, c = im2.shape
    image = np.zeros((max(h1, h2), w1 + w2, 3), dtype=im1.dtype)
    image[0:h1, 0:w1, :] = im1
    image[0:h2, w1:(w1 + w2), :] = im2

    p1 = features.denormalized_image_coordinates(p1, w1, h1)
    p2 = features.denormalized_image_coordinates(p2, w2, h2)
    pl.imshow(image)
    for a, b in zip(p1, p2):
        pl.plot([a[0], b[0] + w1], [a[1], b[1]], 'c')

    pl.plot(p1[:, 0], p1[:, 1], 'ob')
    pl.plot(p2[:, 0] + w1, p2[:, 1], 'ob')


def show_image(image, data):
    # Create figure and axes
    fig,ax = plt.subplots(1)
    im = data.load_image(image)
    print("Show image ", image)
    ax.imshow(im)
    # ax.scatter()
    # plt.show()

def reproject_landmarks(points3D, observations, pose_world_to_cam, 
                        image, camera, data):
    #load the image
    camera_point = pose_world_to_cam.transform_many(points3D)
    points2D = camera.project_many(camera_point)
    fig, ax = plt.subplots(1)
    im = data.load_image(image)
    print("Show image ", image)
    h1, w1, c = im.shape
    # for (idx,pt2D) in enumerate(points2D):
    # print("points2D: ", points2D, " observations: ", observations)
    # print("h1: ", h1, " w1: ", w1)
    pt = features.denormalized_image_coordinates(points2D, w1, h1)
    # print("pt: ", pt)
    # print("observations: ", observations)
    obs = features.denormalized_image_coordinates(observations, w1, h1)
    # print("obs: ", obs)
    # plt.imshow(im)
    ax.imshow(im)
    # plt.show()
    ax.scatter(pt[:, 0], pt[:, 1], c=[[1, 0, 0]])
    ax.scatter(obs[:, 0], obs[:, 1], c=[[0, 1, 0]])
    plt.show()

class SlamTracker(object):

    def __init__(self,  data, config):
        self.slam_matcher = SlamMatcher(config)
        print("init slam tracker")

    def track_reprojection(self, points3D, observations, init_pose, camera,
                           config, data):
        """Estimates the 6 DOF pose with respect to 3D points

        Reprojects 3D points to the image plane and minimizes the
        reprojection error to the correspondences.

        Args:
            points3D: 3D points to reproject
            observations: their 2D correspondences
            init_pose: initial pose depending on the coord. system of points3D
            camera: intrinsic camera parameters
            config, data

        Returns:
            pose: The estimated (relative) 6 DOF pose
        """
        if len(points3D) != len(observations):
            print("len(points3D) != len(observations): ", len(points3D), len(observations))
            return False
        # reproject_landmarks(points3D, observations, init_pose, camera, data)
        # match "last frame" to "current frame"
        # last frame could be reference frame
        # somehow match world points/landmarks seen in last frame
        # to feature matches
        fix_cameras = not config['optimize_camera_parameters']

        chrono = Chronometer()
        ba = csfm.BundleAdjuster()
        # for camera in reconstruction.cameras.values():
        reconstruction._add_camera_to_bundle(ba, camera[1], True)
        # init with a constant motion model!
        # shot == last image
        # shot = reconstruction.shots[last_frame]
        # r = shot.pose.rotation
        # t = shot.pose.translation
        # fix the world pose of the last_frame
        # ba.add_shot(shot.id, 0, r, t, True)

        # constant motion velocity -> just say id
        shot_id = str(0)
        camera_id = str(0)
        camera_const = False
        ba.add_shot(shot_id, str(camera_id), init_pose.rotation, init_pose.translation, camera_const)
        points_3D_constant = True
        # Add points in world coordinates
        for (pt_id, pt_coord) in enumerate(points3D):
            print("point id: ", pt_id, " coord: ", pt_coord)
            ba.add_point(str(pt_id), pt_coord, points_3D_constant)
            ft = observations[pt_id, :]
            print("Adding obs: ", pt_id, ft)
            ba.add_point_projection_observation(shot_id, str(pt_id),
                                                ft[0], ft[1], ft[2])
        #Assume observations N x 3 (x,y,s)
        # for (ft_id, ft) in enumerate(observations):
        #     print("Adding: ", ft_id, ft)
        #     ba.add_point_projection_observation(shot_id, ft_id,
        #                                         ft[0], ft[1], ft[2])
        # gcp = []
        # align_method = config['align_method']
        # if align_method == 'auto':
        #     align_method = align.detect_alignment_constraints(config, reconstruction, gcp)
        # if align_method == 'orientation_prior':
        #     if config['align_orientation_prior'] == 'vertical':
        #         for shot_id in reconstruction.shots:
        #             ba.add_absolute_up_vector(shot_id, [0, 0, -1], 1e-3)
        #     if config['align_orientation_prior'] == 'horizontal':
        #         for shot_id in reconstruction.shots:
        #             ba.add_absolute_up_vector(shot_id, [0, 1, 0], 1e-3)
        print("Added points")
        ba.add_absolute_up_vector(shot_id, [0, 1, 0], 1e-3)
        print("Added add_absolute_up_vector")
        ba.set_point_projection_loss_function(config['loss_function'],
                                              config['loss_function_threshold'])
        print("Added set_point_projection_loss_function")
        ba.set_internal_parameters_prior_sd(
            config['exif_focal_sd'],
            config['principal_point_sd'],
            config['radial_distorsion_k1_sd'],
            config['radial_distorsion_k2_sd'],
            config['radial_distorsion_p1_sd'],
            config['radial_distorsion_p2_sd'],
            config['radial_distorsion_k3_sd'])
        print("Added set_internal_parameters_prior_sd")
        ba.set_num_threads(config['processes'])
        ba.set_max_num_iterations(50)
        ba.set_linear_solver_type("SPARSE_SCHUR")
        print("set_linear_solver_type")
        # for track in graph[shot_id]:
        #     #track = id of the 3D point
        #     if track in reconstruction.points:
        #         point = graph[shot_id][track]['feature']
        #         scale = graph[shot_id][track]['feature_scale']
        #         print("track: ", track, " shot_id: ", shot_id)
        #         print("point: ", point, " scale: ", scale)
        #         ba.add_point_projection_observation(
        #             shot_id, track, point[0], point[1], scale)
        
        # for shot_id in reconstruction.shots:
        #     if shot_id in graph:
        #         for track in graph[shot_id]:
        #             #track = id of the 3D point
        #             if track in reconstruction.points:
        #                 point = graph[shot_id][track]['feature']
        #                 scale = graph[shot_id][track]['feature_scale']
        #                 print("track: ", track, " shot_id: ", shot_id)
        #                 print("point: ", point, " scale: ", scale)
        #                 ba.add_point_projection_observation(
        #                     shot_id, track, point[0], point[1], scale)
        #now match

        
        chrono.lap('setup')
        ba.run()
        chrono.lap('run')

        print("BA finished")

        # for camera in reconstruction.cameras.values():
        # _get_camera_from_bundle(ba, camera)

        # for shot in reconstruction.shots.values():
        s = ba.get_shot(shot_id)
        pose = types.Pose()
        pose.rotation = [s.r[0], s.r[1], s.r[2]]
        pose.translation = [s.t[0], s.t[1], s.t[2]]

        print("Estimated pose: ", pose)
        # for point in reconstruction.points.values():
        #     p = ba.get_point(point.id)
        #     point.coordinates = [p.p[0], p.p[1], p.p[2]]
        #     point.reprojection_errors = p.reprojection_errors
        return True

    # def _track_internal(self, landmarks1, frame1 : Frame, frame2 : str,
    #                     init_pose, camera, config, data):
    def _track_internal(self, frame1 : Frame, frame2 : str, init_pose, camera, config, data):
        """Estimate 6 DOF pose between frame 1 and frame2
        
        Reprojects the landmarks seen in frame 1 to frame2
        and estimates the relative 6 DOF motion between 
        frame1 and frame2 by minimizing the reprojection
        error.

        Arguments:
            landmarks1: 3D points in frame1 to be reprojected
            frame1: image name in dataset
            frame2: image name in dataset
            init_pose: initial 6 DOF estimate
            config, data
        """
        m1, idx1, idx2, matches = self.slam_matcher.match_landmarks_to_image(
                        frame1, frame2, camera, data)
        
        # print("matches: ", m1, matches, idx1, idx2)
        print("landmarks valid idx: ", frame1.idx_valid)
        landmarks1 = frame1.visible_landmarks
        points3D = np.zeros((len(landmarks1), 3))
        # for (l_id, l_coord) in landmarks1:
            # points3D[l_id, :] = l_coord
        print("camera ", camera[1])
        print("# landmarks: ", len(landmarks1.values()))
        idsInFeatures = list(landmarks1.keys())
        for l_id, point in enumerate(landmarks1.values()):
            # print("point ", point.coordinates)
            points3D[l_id, :] = point.coordinates
        print("lengths: idx:", len(m1), len(idx1), len(idx2))
        
        points2D, _, _ = feature_loader.instance.load_points_features_colors(data, frame2, masked=True)
        points2D = points2D[matches[idx2, 1], :]
        # points2D = points2D[idx2, :]
        points3D = points3D[idx1, :] #matches[:, 0]]
        print("m1", m1)
        print("idx1 ", idx1)
        print("idx2 ", idx2)
        
        print("lengths: ", len(points2D), len(points3D))
        reproject_landmarks(points3D, points2D, init_pose, frame2, camera[1], data)

        if len(m1) < 100:
            return False

        #Start tracking
        self.track_reprojection(points3D, points2D, init_pose, camera, config, data)

    def track(self, slam_mapper: SlamMapper, frame: str, config, camera, data):
        """Tracks the current frame with respect to the reconstruction
        """

        """ last_frame, frame, camera, init_pose, config, data):
        Align the current frame to the already estimated landmarks
            (visible in the last frame)
            landmarks visible in last frame
        """

        # Try to match to last frame first
        init_pose = slam_mapper.estimate_pose()
        # success = self._track_internal(
        #                         slam_mapper.last_frame.visible_landmarks,
        #                         slam_mapper.last_frame.im_name, frame,
        #                         init_pose, camera, config, data)
        success = self._track_internal(
                                slam_mapper.last_frame, frame,
                                init_pose, camera, config, data)
        # Now, try to match to last kf
        if slam_mapper.last_frame.frame_id == \
           slam_mapper.last_keyframe.frame_id or not success:

            init_pose = types.Pose()
            success = self._track_internal(
                        slam_mapper.last_keyframe.visible_landmarks,
                        slam_mapper.last_keyframe.im_name,
                        frame, init_pose)



        #prepare the bundle
        

        # tracks are the matched landmarks
        # match landmarks to current frame
        # last frame is typically != last keyframe
        # landmarks contain feature id in last frame
        
        #load feature so both frames
        # p1, f1, _ = 
        #landmarks = LandmarkStorage()

        # for landmark in landmarks:
            # feature_id = landmark.fid
            
        

        # if n_matches < 100: # kind of random number
            # return False

        # velocity = T_(N-1)_(N-2) pre last to last
        # init_pose = T_(N_1)_w * T_(N-1)_W * inv(T_(N_2)_W)
        # match "last frame" to "current frame"
        # last frame could be reference frame
        # somehow match world points/landmarks seen in last frame
        # to feature matches
        # fix_cameras = not config['optimize_camera_parameters']

        #call bundle
        # self.track_reprojection()
