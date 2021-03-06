import os
import re
import sys
import yaml
import json
import glob
import subprocess as sp
from fileseq import FileSequence
import logging as log

debug = True

if debug:
    log.root.setLevel('DEBUG')
else:
    log.root.setLevel('INFO')


class Dailies(object):
    """
    This class combines set of utilities for
    generating media for visual effects review sessions
    This currently include custom mov and slate generation
    """

    def __init__(self):

        script_dir = os.path.dirname(os.path.realpath(__file__))

        # Read module config from yaml file
        config_file = os.path.join(script_dir, 'config.yml')
        with open(config_file, 'r') as f:
            self.config = yaml.load(f)

        self._ffmpeg = os.path.join(script_dir, 'bin', 'ffmpeg')
        self._ffprobe = os.path.join(script_dir, 'bin', 'ffprobe')

        # Use global ffmpeg if it was not installed in this module
        if not os.path.exists(self._ffmpeg):
            self._ffmpeg = 'ffmpeg'
        if not os.path.exists(self._ffprobe):
            self._ffprobe = 'ffprobe'

        # NOTE(Kirill): Probably should move all of this slate related variables
        # to the make_slate function

        # Slate resource files
        self.res = os.path.join(script_dir, 'resources')
        self.bars = os.path.join(self.res, self.config['bars'])
        self.color_bars = os.path.join(self.res, self.config['color_bar'])
        self.logo = os.path.join(self.res, self.config['company_logo'])
        self.logo_font_file = os.path.join(self.res, self.config['company_font'])
        self.font_file = os.path.join(self.res, self.config['body_font'])

        # Global slate alignment properties
        self.left_text_margin = '(w)/2+150'
        self.top_text_margin = '380'
        self.font_size = 40
        self.line_spacing = 40
        self.font_color = 'White'

        self.new_x = '1920'
        self.new_y = '1080'

        # Contains data for all of the dynamic field used on slate
        self.fields_data = {
            'company_name': None,
            'project_name': None,
            'lut': None,
            'shot_name': None,
            'file_name': None,
            'fps': None,
            'frame_range': None,
            'frame_total': None,
            'handles': None,
            'comp_res': None,
            'date': None,
            'user': None,
            'description': None,
        }

        self.tmp_files = []

    def _get_tmp_dir(self):
        """
        :returns: (str) Path to temporary file directory for specific platform
        """
        tmp = None
        if sys.platform == 'darwin' or 'linux' in sys.platform:
            tmp = os.path.abspath(os.environ.get('TMPDIR'))
        elif sys.platform == 'win32':
            tmp = os.path.abspath(os.environ.get('TEMP')).replace(os.sep, '/')
            # On Windows, some usernames are shortened with a tilde.
            # Example: EVILEY~1 instead of evileye_52
            import getpass
            tmp = tmp.split('/')
            for item in tmp:
                if '~1' in item:
                    tmp[tmp.index(item)] = getpass.getuser()
            tmp = '/'.join(tmp)
        return tmp

    def _get_tmp_file(self, name):
        """
        This function does not create the actual file it only creates
        a temp folder for it and return the full path to use by the application

        :param name: (str) Name of desired temp file
        :returns: (str) Path to temporary file
        """
        tmp_dir = self._get_tmp_dir()
        if not os.path.exists(tmp_dir):
            os.mkdirs(tmp_dir)
        temp_file_path = os.path.join(tmp_dir, name)
        self.tmp_files.append(temp_file_path)

        return temp_file_path

    def _get_seq(self, path):
        """
        Crate file sequence object by given a file sequence path such as
        /path/image.%04d.dpx

        :param path: (str) File sequence path

        :returns: File Sequence object
        """
        s = re.sub(r'%[0-9]+d', '#', path)
        seq = FileSequence.findSequenceOnDisk(s)

        return seq

    def fields_from_dict(self, fields_dict):
        """
        Populate slate fields. Run before creating a slate
        """
        # TODO(Kirill): Made this a part of the make_slate function?
        for k, v in self.fields_data.items():
            self.fields_data[k] = fields_dict[k]

    def get_media_info(self, path):
        """
        (Kirill) This function is currently not used!

        Get information about movie file by using ffprobe

        :returns: (dict) Dictionary with media info about video stream
                         See ffprobe docs for more information
        """
        cmd = [
            str(self._ffprobe), '-v', 'quiet', '-select_streams', 'v',
            '-show_streams', '-print_format', 'json', str(path)
        ]

        output = None
        stream = {}

        try:
            result = sp.check_output(cmd)
            output = json.loads(result)
        except sp.CalledProcessError as e:
            log.error('ffprobe failed to extract information about the asset. %s' % e)
            log.debug('Test this command: %s' % ' '.join(cmd))
            raise
        except Exception as e:
            log.error('Error happened while excuting CMD command. ' + str(e))
            log.debug('Test this command: %s' % ' '.join(cmd))
            raise

        if not output:
            log.warning('No media streams are found in %s' % path)
            return stream

        if len(output.get('streams')) == 1:
            stream = output['streams'][0]
        elif len(output.get('streams')) > 1:
            log.warning(
                'Media file %s contains more then one streams. '
                'Using the first one. '
            )
            stream = output['streams'][0]

        return stream

    def make_slate(self, src_seq):
        """
        Generate an image slate out of given image sequence
        Slate information get set from self.fields_data member variable

        :param src_seq: (str) Path to source image sequence in the following format /path/name_%04d.ext

        :returns: (str) Path to generated slate image
        """

        output = self._get_tmp_file('tmp_slate.png')
        seq = self._get_seq(src_seq)

        # Alignment properties for slate field
        p = "x={left_text_margin}-text_w:y={top_text_margin}+{line_spacing}".format(
            left_text_margin=self.left_text_margin,
            top_text_margin=self.top_text_margin,
            line_spacing=self.line_spacing
        )

        # Alignment properties for slate field value
        pv = "x={left_text_margin}+10:y={top_text_margin}+{line_spacing}".format(
            left_text_margin=self.left_text_margin,
            top_text_margin=self.top_text_margin,
            line_spacing=self.line_spacing
        )

        # Slate main body text style
        text = "drawtext=fontsize={font_size}:fontcolor={font_color}:fontfile='{font_file}':text".format(
            font_size=self.font_size,
            font_color=self.font_color,
            font_file=self.font_file
        )

        # ffmpeg complex filter to generate a slate. For more information see
        # section four (Filtergraph description) of the following docs
        # https://ffmpeg.org/ffmpeg-filters.html
        filters = (
            "[1:v] scale={new_x}:{new_y}, setsar=1:1 [base]; "
            "[0:v] scale={new_x}:{new_y} [thumbnail]; "
            "[thumbnail][3:v] overlay [thumbnail]; "
            "[thumbnail][3:v] overlay=x=(main_w-overlay_w):y=(main_h-overlay_h) [thumbnail]; "
            "[thumbnail] scale=(iw/4):(ih/4) [thumbnail]; "
            "[base][thumbnail] overlay=((main_w-overlay_w)/2)-500:(main_h-overlay_h)/2 [base]; "
            "[2:v] scale=-1:-1 [self.bars]; "
            "[base][self.bars] overlay=x=(main_w-overlay_w):y=(main_h-overlay_h-50) [base]; "
            "[4:v] scale=(iw*0.2):(ih*0.2) [self.logo]; "
            "[base][self.logo] overlay=x=500:y=100 [base]; "
            "[base] "
              "drawtext=fontsize=80:fontcolor={font_color}:fontfile={logo_font_file}:text={company_name}:x=690:y=130, "
              "drawtext=fontsize=50:fontcolor={font_color}:fontfile={font_file}:text={project_name}:x=(w)/2:y=250, "
                   "{text}='LUT\: ':{p}*0, "
                   "{text}={lut}:{pv}*0, "
                   "{text}='Shot name\: ':{p}*1, "
                   "{text}={shot_name}:{pv}*1, "
                   "{text}='File name\: ':{p}*2, "
                   "{text}={file_name}:{pv}*2, "
                   "{text}='FPS\: ':{p}*3, "
                   "{text}={fps}:{pv}*3, "
                   "{text}='Frame range\: ':{p}*4, "
                   "{text}={frame_range}:{pv}*4, "
                   "{text}='Frame total\: ':{p}*5, "
                   "{text}={frame_total}:{pv}*5, "
                   "{text}='Handles\: ':{p}*6, "
                   "{text}={handles}:{pv}*6, "
                   "{text}='Comp resolution\: ':{p}*7, "
                   "{text}={comp_res}:{pv}*7, "
                   "{text}='Date\: ':{p}*8, "
                   "{text}={date}:{pv}*8, "
                   "{text}='User\: ':{p}*9, "
                   "{text}={user}:{pv}*9, "
                   "{text}='Description\: ':{p}*10, "
                   "{text}={description}:{pv}*10 "
        ).format(
            #
            # Global formatting and render values
            font_color=self.font_color, logo_font_file=self.logo_font_file,
            font_file=self.font_file, line_spacing=self.line_spacing,
            left_text_margin=self.left_text_margin,
            top_text_margin=self.top_text_margin, new_x=self.new_x,
            new_y=self.new_y, text=text, p=p, pv=pv,
            #
            # User defined fields slate values
            project_name=self.fields_data['project_name'],
            company_name=self.fields_data['company_name'],
            lut=self.fields_data['lut'],
            shot_name=self.fields_data['shot_name'],
            file_name=self.fields_data['file_name'],
            fps=self.fields_data['fps'],
            frame_range=self.fields_data['frame_range'],
            frame_total=self.fields_data['frame_total'],
            handles=self.fields_data['handles'],
            comp_res=self.fields_data['comp_res'],
            date=self.fields_data['date'],
            user=self.fields_data['user'],
            description=self.fields_data['description']
        )

        cmd = [
            self._ffmpeg, '-v', 'quiet', '-y', '-start_number', str(seq.start()), '-i', str(src_seq),
            '-f', 'lavfi', '-i', 'color=c=black', '-i', self.bars, '-i', self.color_bars,
            '-i', self.logo, '-vframes', '1', '-filter_complex', filters, str(output)
        ]

        if debug:
            cmd.pop(1)
            cmd.pop(1)
            log.debug('SLATE_COMMAND: %s' % cmd)

        sp.call(cmd)

        #TODO)Kirill) Check for errors and clean exit
        # Remove temp files

        return output

    def make_mov(self, src_seq, out_mov, preset='', burnin=True, slate=True):
        """
        Generate movie out of image sequence with and optional slate and burnins

        :param src_seq: (str) Path to a file sequence /path/image.%04d.png
        :param out_mov: (str) Output path for generated movie file
        :param preset: (str) Name of video preset from 'config.yml'
        :param burnin: (bool) Generate burn in text with file name and frame
                       number on every frame of the video
        :param slate: (bool) Generate slate image and append it as the first
                      frame of the final video

        :returns: (str) Path to generated movie file
        """

        # Get video settings for ffmpeg from the configuration file
        video_presets = self.config['video_pressets']
        video_settings = video_presets.get(preset)

        if video_settings is not None:
            video_settings = video_settings.split(' ')
        else:
            # Use default settings
            video_settings = [
                '-crf', '18', '-vcodec', 'mjpeg', '-pix_fmt', 'yuvj444p',
                '-qmin', '1', '-qmax', '1', '-r', '24'
            ]

        seq = self._get_seq(src_seq)

        parent, file_name = os.path.split(src_seq)

        filters = (
            "[1:v] scale={new_x}:{new_y}, setsar=1:1 [base]; "
            "[base] null "
        ).format(new_x=self.new_x, new_y=self.new_y)

        if slate:
            # Concatenate our slate and the rest of the video
            slate_filter = (
                "[base]; "
                "[0:v] trim=start_frame=0:end_frame=1 [slate]; "
                "[slate][base] concat "
            )
            filters += slate_filter

        if burnin:
            # Add burin text to the filter
            # This filter generate text with original sequence file name
            # and frame number on the every frame of the video
            burnin_filter = (
                "[base]; [base] "
                  # Left button sequence name
                  "drawtext=fontsize=30: "
                  "fontcolor={font_color}: "
                  "fontfile={font_file}: "
                  "expansion=none: "
                  "text={file_name}: "
                  "x=10:y=(h-(text_h+10)): "
                  "enable='between(n,1,99999)', "
                  # Right button frame counter
                  "drawtext=fontsize=30: "
                  "fontcolor={font_color}: "
                  "fontfile={font_file}: "
                  "start_number=1000: "
                  "text=@frame_number \[{start}-{end}\]: "
                  "x=(w-(text_w+10)):y=(h-(text_h+10)): "
                  "enable='between(n,1,99999)'"
            ).format(
                font_color=self.font_color, font_file=self.font_file,
                file_name=file_name, start=seq.start(), end=seq.end()
            )
            filters += burnin_filter

        # Replace this frame number variable separately
        # since it conflict with the string format function tokens
        filters = filters.replace('@frame_number', '%{n}')

        # Generate an mov with the attached slate
        cmd = [self._ffmpeg, '-v', 'quiet', '-y']

        if slate:
            # Generate slate image
            slate = self.make_slate(src_seq)

            # Append slate stream as stream 0 to the final command
            cmd += ['-i', slate]
        else:
            # Append null source to not mess up indexes if the input for the filters
            cmd += ['-f', 'lavfi', '-i', 'nullsrc=s=256x256:d=5']

        cmd += ['-start_number', str(seq.start()), '-i', src_seq]
        cmd += video_settings
        cmd += ['-filter_complex', filters, out_mov]

        if debug:
            # Remove silent flags from the final command
            cmd.pop(1)
            cmd.pop(1)
            log.debug('MOV_COMMAND: %s' % cmd)

        sp.call(cmd)

        #TODO)Kirill) Check for errors and clean exit

        return out_mov
