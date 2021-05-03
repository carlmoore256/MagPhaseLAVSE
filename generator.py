import tensorflow as tf
import utils
import cv2
import glob
import os
import numpy as np

class DataGenerator():

    # num vid frames -> how many video frames to extract flow data from, size of 4D tensor
    def __init__(self, batch_size, num_vid_frames=4, framerate=30, samplerate=16000, data_path="./data/raw"):

        assert batch_size > 1

        self.batch_size = batch_size
        self.num_vid_frames = num_vid_frames
        self.framerate = framerate
        self.samplerate = samplerate

        self.noise_stddev = 1.0

        self.normalize_fft = True

        # largest power of 2 that fits
        # self.spectrogram_len = 

        self.all_vids = utils.get_all_files(data_path, "mp4")
        self.all_audio = utils.get_all_files(data_path, "wav")
        self.current_av_pair = self.load_example_pair(self.all_vids[0])

        self.example_idx = 0


    def add_noise(self, audio):
        noise = tf.random.normal(audio.shape, mean=0.0, stddev=self.noise_stddev, dtype=tf.dtypes.float32)
        a_noise = tf.math.add(audio, noise)
        return a_noise

    # returns a random num_vid_frames frames from video, returns FFT and vid
    def get_random_clip(self, frames, audio):
        frame_start = np.random.randint(0,frames.shape[0]-self.num_vid_frames-1)
        frame_end = frame_start+self.num_vid_frames

        v_clip = frames[frame_start:frame_end]

        sample_start = int((frame_start/self.framerate) * self.samplerate)
        sample_end = int((frame_end/self.framerate) * self.samplerate)

        a_clip = audio[sample_start:sample_end]

        return v_clip, a_clip

    # waveform audio -> FFT (tf.complex64 dtype)
    def fft(self, audio):
        audio = tf.cast(audio, dtype=tf.complex64)
        fft = tf.signal.fft(audio)
        if self.normalize:
            fft = self.normalize_fft(fft)
        return fft

    # normalize fft by 1/(length/2) 
    def normalize_fft(self, fft):
        scalar = 1.0/(fft.shape[0] // 2)
        normalized_fft = tf.math.multiply(fft, scalar)
        return normalized_fft

    def reverse_normalize_fft(self, normalized_fft):
        return normalized_fft * (normalized_fft.shape[0] * 2)

    # x + y(i) -> magnitude, angle
    def rectangular_to_polar(self, rectangular):
        magnitude = tf.abs(rectangular)
        angle = tf.math.angle(rectangular)
        polar = tf.concat([magnitude, angle], axis=2)
        return polar

    def polar_to_rectangular(self, polar):
        real = polar[:, :, 0] * np.cos(polar[:, :, 1])
        imag = polar[:, :, 1] * np.cos(polar[:, :, 1])
        concat = tf.concat([real, imag], axis=-1)
        cmplx = self.ri_to_complex(concat)
        return cmplx

    # float32 tensor to rectangular notation:
    # [real, imaginary] -> [complex,]
    # def complex_to_ri(self, tensor):      
    #     real = tf.math.real(tensor)
    #     imag = tf.math.imag(tensor)
    #     ri_t = tf.concat([real, imag], axis=2)
    #     return ri_t

    # rectangular notation to float32 tensor
    # [complex,] -> [real, imaginary]
    def ri_to_complex(self, tensor):      
        real = tensor[:,:,0]
        imag = tensor[:,:,1]
        # account for FFT mirror cutoff at N/2+1
        mirror = tf.zeros_like(real)
        real = tf.concat([real,mirror], axis=1)
        imag = tf.concat([imag,mirror], axis=1)
        complex_t = tf.dtypes.complex(real, imag)
        return complex_t


    # load audio and video exaple pair
    def load_example_pair(self, vid_path):

        split_path = os.path.split(vid_path)
        name = split_path[-1][:-4]
        name = name + ".wav"
        print(os.path.split(split_path[0])[0])
        audio_path = os.path.join(os.path.split(split_path[0])[0], "audio/", name)
        print(audio_path)

        frames = self.load_video(vid_path)
        audio = self.load_audio(audio_path)

        print(f'FRAMES SHAPE {frames.shape}')
        print(f'AUDIO SHAPE {audio.shape}')

        return frames, audio

    def load_video(self, path):
        cap = cv2.VideoCapture(path)
        frames = []
        while(cap.isOpened()):
            ret, frame = cap.read()
            frames.append(frame)
            if ret is False:
                break
        cap.release()
        # frames = tf.convert_to_tensor(frames)
        frames = np.asarray(frames)
        print("\n LOADED VID \n")
        return frames

    def load_audio(self, path):
        raw_audio = tf.io.read_file(path)
        waveform = tf.audio.decode_wav(raw_audio, desired_channels=1)
        return waveform[0]

    # main process for generating x,y pairs
    def gen_xy(self, frames, audio):
        v_clip, a_clip = self.get_random_clip(frames, audio)
        a_clip_noise = self.add_noise(a_clip)
        # take fft of audio & convert from rectangular (x + y(i)) into polar (magnitude, phase)
        # added noise
        ft_polar_x = self.rectangular_to_polar(self.fft(a_clip_noise))
        # ground truth
        fft_polar_y = self.rectangular_to_polar(self.fft(a_clip))

        return ft_polar_x, fft_polar_y, v_clip

    def generator(self):
        while True:
            frames, audio = self.load_example_pair(self.all_vids[self.example_idx])

            self.example_idx += 1

            if self.example_idx > len(self.all_vids):
                self.example_idx = 0

            x_ft = []
            y_ft = []

            vid = []

            # x_ft, y_ft, v_clip = self.gen_xy(frames, audio)


            # x_ft = tf.expand_dims(x_ft, axis=0)
            # x_vid = tf.expand_dims(v_clip, axis=0)

            # y_ft = tf.expand_dims(y_ft, axis=0)
            # y_vid = tf.expand_dims(v_clip, axis=0)

            # creates batch on the same video
            for _ in range(self.batch_size - 1):
                this_x_ft, this_y_ft, this_v_clip = self.gen_xy(frames, audio)

                x_ft.append(this_x_ft)
                y_ft.append(this_y_ft)
                vid.append(this_v_clip)
                
                # x_ft = tf.concat([x_ft, this_x_ft], 0)
                # y_ft = tf.concat([y_ft, this_y_ft], 0)

                # x_vid = tf.concat([x_vid, this_v_clip], 0)
                # y_vid = tf.concat([y_vid, this_v_clip], 0)

                # x.append([fft_x, v_clip])
                # y.append([fft_y, v_clip])

            x_ft = tf.convert_to_tensor(x_ft)
            y_ft = tf.convert_to_tensor(y_ft)
            vid = tf.convert_to_tensor(vid)

            return [[x_ft, vid], [y_ft, vid]]
            # return [[x_ft, x_vid], [y_ft, y_vid]] 

            # x = np.asarray(x)
            # y = np.asarray(y)

if __name__ == "__main__":
    dg = DataGenerator(
    batch_size = 4,
    num_vid_frames = 4,
    framerate = 30,
    samplerate = 16000,
    data_path = "./data/raw"
    )
    gen = dg.generator()

    print(next(gen))