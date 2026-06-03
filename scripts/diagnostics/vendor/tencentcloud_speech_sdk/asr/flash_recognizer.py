import base64
import hashlib
import hmac
import time

import requests


class FlashRecognitionRequest:
    def __init__(self, engine_type):
        self.engine_type = engine_type
        self.speaker_diarization = 0
        self.hotword_id = ""
        self.hotword_list = ""
        self.input_sample_rate = 0
        self.customization_id = ""
        self.filter_dirty = 0
        self.filter_modal = 0
        self.filter_punc = 0
        self.convert_num_mode = 1
        self.word_info = 0
        self.voice_format = ""
        self.first_channel_only = 1
        self.reinforce_hotword = 0
        self.sentence_max_length = 0
        self.replace_text_id = ""

    def set_first_channel_only(self, first_channel_only):
        self.first_channel_only = first_channel_only

    def set_speaker_diarization(self, speaker_diarization):
        self.speaker_diarization = speaker_diarization

    def set_filter_dirty(self, filter_dirty):
        self.filter_dirty = filter_dirty

    def set_filter_modal(self, filter_modal):
        self.filter_modal = filter_modal

    def set_filter_punc(self, filter_punc):
        self.filter_punc = filter_punc

    def set_convert_num_mode(self, convert_num_mode):
        self.convert_num_mode = convert_num_mode

    def set_word_info(self, word_info):
        self.word_info = word_info

    def set_hotword_id(self, hotword_id):
        self.hotword_id = hotword_id

    def set_hotword_list(self, hotword_list):
        self.hotword_list = hotword_list

    def set_input_sample_rate(self, input_sample_rate):
        self.input_sample_rate = input_sample_rate

    def set_customization_id(self, customization_id):
        self.customization_id = customization_id

    def set_voice_format(self, voice_format):
        self.voice_format = voice_format

    def set_sentence_max_length(self, sentence_max_length):
        self.sentence_max_length = sentence_max_length

    def set_reinforce_hotword(self, reinforce_hotword):
        self.reinforce_hotword = reinforce_hotword

    def set_replace_text_id(self, replace_text_id):
        self.replace_text_id = replace_text_id


class FlashRecognizer:
    def __init__(self, appid, credential):
        self.credential = credential
        self.appid = appid

    def _format_sign_string(self, param):
        signstr = "POSTasr.cloud.tencent.com/asr/flash/v1/"
        for t in param:
            if "appid" in t:
                signstr += str(t[1])
                break
        signstr += "?"
        for x in param:
            if "appid" in x:
                continue
            for t in x:
                signstr += str(t)
                signstr += "="
            signstr = signstr[:-1]
            signstr += "&"
        signstr = signstr[:-1]
        return signstr

    def _build_header(self):
        return {"Host": "asr.cloud.tencent.com"}

    def _sign(self, signstr, secret_key):
        hmacstr = hmac.new(
            secret_key.encode("utf-8"),
            signstr.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        return base64.b64encode(hmacstr).decode("utf-8")

    def _build_req_with_signature(self, secret_key, params, header):
        query = sorted(params.items(), key=lambda d: d[0])
        signstr = self._format_sign_string(query)
        signature = self._sign(signstr, secret_key)
        header["Authorization"] = signature
        requrl = "https://" + signstr[4:]
        return requrl, signstr

    def _create_query_arr(self, req):
        query_arr = {
            "appid": self.appid,
            "secretid": self.credential.secret_id,
            "timestamp": str(int(time.time())),
            "engine_type": req.engine_type,
            "voice_format": req.voice_format,
            "speaker_diarization": req.speaker_diarization,
            "customization_id": req.customization_id,
            "filter_dirty": req.filter_dirty,
            "filter_modal": req.filter_modal,
            "filter_punc": req.filter_punc,
            "convert_num_mode": req.convert_num_mode,
            "word_info": req.word_info,
            "first_channel_only": req.first_channel_only,
            "reinforce_hotword": req.reinforce_hotword,
            "sentence_max_length": req.sentence_max_length,
        }
        if req.hotword_id != "":
            query_arr["hotword_id"] = req.hotword_id
        if req.hotword_list != "":
            query_arr["hotword_list"] = req.hotword_list
        if req.input_sample_rate != 0:
            query_arr["input_sample_rate"] = req.input_sample_rate
        if req.replace_text_id != "":
            query_arr["replace_text_id"] = req.replace_text_id
        return query_arr

    def recognize(self, req, data):
        header = self._build_header()
        query_arr = self._create_query_arr(req)
        req_url, _signstr = self._build_req_with_signature(
            self.credential.secret_key, query_arr, header
        )
        return requests.post(req_url, headers=header, data=data)
