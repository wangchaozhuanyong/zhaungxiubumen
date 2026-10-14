"""Offline unit contracts only. No real voice selection, platform result or lexicon mutation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import narration_audio as audio
from narration_contract import validate_narration, validate_narration_evidence, validate_subtitle_cues, validate_subtitle_html, SUBTITLE_POLICY

class NarrationContractTests(unittest.TestCase):
    def contract(self):
        return {"presentation_mode": "copy_led", "copy_mode": "narrative", "timing_driver": "narration",
            "duration_seconds": 52, "audio_required": True, "music_required": True,
            "narration": {"enabled": True, "language": "zh-CN", "voice_profile_id": "B"}}
    def test_absent_or_disabled_preserves_old_28_second_route(self):
        self.assertEqual(validate_narration({"duration_seconds":28}), [])
        self.assertEqual(validate_narration({"narration":{"enabled":False},"duration_seconds":28}), [])
    def test_narration_flag_must_not_be_truthy_string(self):
        self.assertTrue(validate_narration({"narration":{"enabled":"false"}}))
    def test_copy_led_narrative_and_voice_timing_required(self):
        for changes in [{"presentation_mode":"visual_music"},{"copy_mode":"none"},{"timing_driver":"music"}]:
            self.assertTrue(validate_narration({**self.contract(),**changes}))
    def test_only_chinese_voice_allowed(self):
        c = self.contract(); c["narration"]["language"] = "en-US"
        self.assertIn("narration_language_must_be_zh_CN",validate_narration(c))
    def test_default_voice_is_never_chosen(self):
        c = self.contract(); c["narration"]["voice_profile_id"] = None
        self.assertIn("narration_fixed_voice_selection_required",validate_narration(c))
    def test_audition_does_not_require_owner_voice_or_full_video_length(self):
        c = self.contract(); c.update(stage="five_voice_auditions_before_owner_selection",duration_seconds=22)
        c["narration"]["voice_profile_id"] = None
        self.assertEqual(validate_narration(c),[])
    def test_no_music_or_audio_silent_fallback(self):
        for key in ["audio_required","music_required"]:
            c=self.contract(); c[key]=False
            self.assertTrue(validate_narration(c))
    def test_actual_mode_range_and_not_nan(self):
        for duration in [30,44.99,60.01,float("nan"),None]:
            c=self.contract(); c["duration_seconds"]=duration
            self.assertTrue(validate_narration(c))
        for duration in [45,52,60]:
            c=self.contract();c["duration_seconds"]=duration
            self.assertEqual(validate_narration(c),[])
    def test_final_requires_actual_audio_alignment_and_mix_references(self):
        errors=validate_narration(self.contract(),final=True)
        self.assertEqual(len(errors),6)
        self.assertIn("narration_full_burned_in_bilingual_subtitles_required", errors)
    def test_single_unchanged_picture_rejected(self):
        scene={"id":"s","source_asset_ids":["a"],"narration_line_ids":["n"],"spoken_visual_evidence":"柜体同一全景"}
        self.assertIn("narration_cannot_use_one_unchanged_visual_for_entire_voice",
            validate_narration(self.contract(),{"scenes":[scene,dict(scene)]}))
    def test_same_photo_with_real_detail_information_allowed(self):
        base={"source_asset_ids":["a"],"narration_line_ids":["n"]}
        self.assertEqual(validate_narration(self.contract(),{"scenes":[{**base,"spoken_visual_evidence":"挂衣分区可见"},
            {**base,"spoken_visual_evidence":"同源铰链原图裁切放大"}]}),[])
    def test_each_segment_needs_line_and_visible_evidence(self):
        self.assertTrue(validate_narration(self.contract(),{"scenes":[{},{}]}))
    def test_final_cannot_claim_complete_from_paths_without_hashes(self):
        self.assertTrue(validate_narration_evidence(self.contract(),audio.ROOT))

class NarrationSubtitleTests(unittest.TestCase):
    def timing(self):
        return {"lines":[{"id":"n1","text":"柜体收口，先问是否包含安装。","start":1,"end":5}]}
    def document(self):
        return {"policy_version":SUBTITLE_POLICY,"audio_offset_seconds":1/30,"cues":[
            {"id":"c1","line_id":"n1","zh":"柜体收口","en":"Cabinet finishing","start":1+1/30,"end":2.5},
            {"id":"c2","line_id":"n1","zh":"先问是否包含安装。","en":"Check whether installation is included.","start":2.5,"end":5+1/30}]}
    def test_full_short_cues_and_audio_offset_allowed(self):
        self.assertEqual(validate_subtitle_cues(self.document(),self.timing(),6),[])
    def test_summary_is_not_full_subtitles(self):
        d=self.document();d["cues"][1]["zh"]="问清安装"
        self.assertTrue(any("incomplete_spoken_coverage" in e for e in validate_subtitle_cues(d,self.timing(),6)))
    def test_no_cues_rejected(self):
        d=self.document();d["cues"]=[]
        self.assertTrue(validate_subtitle_cues(d,self.timing(),6))
    def test_english_empty_rejected(self):
        d=self.document();d["cues"][0]["en"]=" "
        self.assertTrue(validate_subtitle_cues(d,self.timing(),6))
    def test_duplicate_or_unknown_id_rejected(self):
        for field,value in [("id","c1"),("line_id","unknown")]:
            d=self.document();d["cues"][1][field]=value
            self.assertTrue(validate_subtitle_cues(d,self.timing(),6))
    def test_nan_overlap_wrong_sync_or_outside_video_rejected(self):
        for field,value in [("start",float("nan")),("start",2.0),("end",8)]:
            d=self.document();d["cues"][1][field]=value
            self.assertTrue(validate_subtitle_cues(d,self.timing(),6))
        d=self.document();d["audio_offset_seconds"]=float("nan")
        self.assertTrue(validate_subtitle_cues(d,self.timing(),6))
    def test_missing_first_or_last_spoken_time_rejected(self):
        for index,field,value in [(0,"start",1.8),(1,"end",4.2)]:
            d=self.document();d["cues"][index][field]=value
            self.assertTrue(validate_subtitle_cues(d,self.timing(),6))
    def test_numeric_word_cannot_be_silently_removed(self):
        t=self.timing();t["lines"][0]["text"]="柜体收口，先问是否包含2次安装。"
        self.assertTrue(validate_subtitle_cues(self.document(),t,6))
    def test_srt_only_or_disabled_cannot_pass_final(self):
        c=NarrationContractTests().contract()
        for subs in [{"enabled":False},{"enabled":True,"mode":"external_srt"}]:
            c["narration"]["subtitles"]=subs
            self.assertIn("narration_full_burned_in_bilingual_subtitles_required",validate_narration(c,final=True))
    def html(self):
        return "".join('<div id="'+c["id"]+'" class="clip narration-subtitle" data-cue-id="'+c["id"]+'" data-start="'+str(c["start"])+'" data-duration="'+str(c["end"]-c["start"])+'" data-track-index="70"><p class="subtitle-zh">'+c["zh"]+'</p><p class="subtitle-en">'+c["en"]+'</p></div>' for c in self.document()["cues"])
    def test_html_real_clip_declarations_match_cues(self):
        self.assertEqual(validate_subtitle_html(self.html(),self.document()),[])
    def test_html_chapter_titles_only_or_missing_english_fail(self):
        self.assertTrue(validate_subtitle_html('<div class="note">要点标题</div>',self.document()))
        self.assertTrue(validate_subtitle_html(self.html().replace('subtitle-en','chapter-en'),self.document()))
    def test_html_wrong_time_or_text_fail(self):
        self.assertTrue(validate_subtitle_html(self.html().replace('data-duration="', 'data-duration="9'),self.document()))
        self.assertTrue(validate_subtitle_html(self.html().replace('柜体收口','柜体'),self.document()))

class AudioBoundaryTests(unittest.TestCase):
    def setUp(self):
        parent=audio.ROOT/"drafts/creative/.test-sandboxes"
        parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_path_cannot_escape_project(self):
        with self.assertRaisesRegex(ValueError,"path_must_belong"):
            audio.project_path("/private/tmp/no-audio-write")
    def test_disk_keep_eight_gib_after_all_pending_bytes(self):
        with mock.patch.object(audio.shutil,"disk_usage",return_value=mock.Mock(free=9*audio.GIB)):
            with self.assertRaisesRegex(ValueError,"KEEP_8_GIB"):
                audio.reserve_disk(2*audio.GIB)
            self.assertGreater(audio.reserve_disk()["free_bytes"],8*audio.GIB)
    def test_no_selected_profile_blocks_without_any_model_load(self):
        with mock.patch.object(audio,"load_json",return_value={"active_voice_profile_id":None,"status":"AWAITING_OWNER_SELECTION"}):
            with self.assertRaisesRegex(ValueError,"VOICE_SELECTION_REQUIRED"):
                audio.active_profile()
    def test_json_output_is_exclusive_not_overwrite(self):
        path=self.root/"result.json";audio.write_json(path,{"status":"fixture"})
        before=path.read_bytes()
        with self.assertRaises(FileExistsError):audio.write_json(path,{"status":"wrong"})
        self.assertEqual(before,path.read_bytes())
    def test_mix_rejects_invalid_parameters_before_running_ffmpeg(self):
        for gap,ratio in [(float('nan'),1.6),(12,float('inf')),(5,1.6),(31,1.6),(12,.9),(12,6.1)]:
            with mock.patch.object(audio.subprocess,'run') as execute:
                with self.assertRaisesRegex(ValueError,'mix_parameters_invalid'):
                    audio.mix(self.root/'voice.wav',self.root/'music.wav',self.root/'mix.wav',
                              music_below_voice_db=gap,ducking_ratio=ratio)
                execute.assert_not_called()
    def test_mix_uses_audible_music_defaults_and_measures_actual_excerpt(self):
        voice=self.root/'voice.wav';music=self.root/'music.wav'
        voice.write_bytes(b'fixture-voice');music.write_bytes(b'fixture-music')
        output=self.root/'mixed.wav'
        with mock.patch.object(audio,'audio_metadata',return_value={'duration_seconds':10}), \
             mock.patch.object(audio,'loudness',side_effect=[{'input_i':'-16'},{'input_i':'-9'},{'input_i':'-16','input_tp':'-2'}]) as measure, \
             mock.patch.object(audio.subprocess,'run') as execute:
            result=audio.mix(voice,music,output)
        self.assertEqual(measure.call_args_list[1],mock.call(music,10))
        self.assertEqual(result['initial_music_below_voice_db'],12)
        self.assertEqual(result['ducking']['ratio'],1.6)
        self.assertEqual(result['music_gain_db'],-19)
        command=execute.call_args.args[0];filt=command[command.index('-filter_complex')+1]
        self.assertIn('threshold=0.08:ratio=1.6',filt)
        self.assertIn('volume=-19.0dB',filt)
        self.assertEqual(result['complete_human_listening'],'NOT_PERFORMED_BY_THIS_COMMAND')
    def test_mix_custom_level_is_recorded_and_does_not_loop(self):
        voice=self.root/'v.wav';music=self.root/'m.wav'
        voice.write_bytes(b'v');music.write_bytes(b'm')
        with mock.patch.object(audio,'audio_metadata',return_value={'duration_seconds':8}), \
             mock.patch.object(audio,'loudness',side_effect=[{'input_i':'-16'},{'input_i':'-8'},{'input_i':'-16','input_tp':'-2'}]), \
             mock.patch.object(audio.subprocess,'run'):
            result=audio.mix(voice,music,self.root/'out.wav',music_below_voice_db=14,ducking_ratio=2)
        self.assertEqual(result['initial_music_below_voice_db'],14)
        self.assertEqual(result['ducking']['ratio'],2)
        self.assertFalse(result['music_looped'])
    def test_loudness_duration_guard_precedes_subprocess(self):
        with mock.patch.object(audio.subprocess,'run') as execute:
            with self.assertRaisesRegex(ValueError,'loudness_duration_invalid'):
                audio.loudness(self.root/'x.wav',float('nan'))
            execute.assert_not_called()
    def test_selection_needs_actual_owner_choice_not_recommendation(self):
        ref=self.root/"ref.json";auth=self.root/"auth.json"
        audio.write_json(ref,{"id":"B"});audio.write_json(auth,{"status":"RECOMMENDED_LISTEN_FIRST","voice_id":"B"})
        with self.assertRaisesRegex(ValueError,"actual_owner_voice_selection"):
            audio.select_profile(ref,auth,self.root/"receipt.json")
    def test_copy_gate_cannot_be_sandbox_or_predicted_result(self):
        with mock.patch("public_copy_guard.check",return_value={"status":"PASS_SANDBOX_ONLY"}):
            with self.assertRaisesRegex(ValueError,"qingdou_copy_gate_not_passed"):
                audio.require_copy_gate(self.root/"package.json")
    def test_timeline_binds_changed_audio_not_only_words(self):
        af=self.root/"audio.wav";af.write_bytes(b"fixture-not-real-audio")
        tf=self.root/"text.txt";tf.write_text("衣柜收纳")
        alignment=self.root/"alignment.json"
        audio.write_json(alignment,{"audio":audio.pin(af),"text":audio.pin(tf),"words":[
            {"text":"衣柜","start":0,"end":1},{"text":"收纳","start":1.1,"end":2}]})
        lines=self.root/"lines.json";audio.write_json(lines,{"lines":[{"id":"n1","text":"衣柜"},{"id":"n2","text":"收纳"}]})
        output=self.root/"timing.json";result=audio.timeline(alignment,lines,output)
        self.assertEqual(result["lines"][1]["start"],1.1)
        self.assertFalse(result["visual_sync_measured"])
        af.write_bytes(b"changed-fixture")
        with self.assertRaisesRegex(ValueError,"alignment_source_changed"):
            audio.timeline(alignment,lines,self.root/"other.json")

if __name__=="__main__":unittest.main()
