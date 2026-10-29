/* Piano-only float renderer, adapted from the previous project TinySoundFont
 * preview. TinySoundFont/TinyMidiLoader are MIT; headers/licenses retained. */
#define TSF_IMPLEMENTATION
#include "tsf.h"
#define TML_IMPLEMENTATION
#include "tml.h"
#include <stdio.h>
#include <stdint.h>
#include <math.h>
static void u16(FILE*f,unsigned v){fputc(v&255,f);fputc((v>>8)&255,f);}
static void u32(FILE*f,unsigned v){u16(f,v&65535);u16(f,v>>16);}
int main(int argc,char**argv){
  if(argc!=4){fprintf(stderr,"usage: rich_piano_render bank.sf2 performance.mid dry-float.wav\n");return 2;}
  tsf*font=tsf_load_filename(argv[1]);tml_message*song=tml_load_filename(argv[2]);
  if(!font||!song)return 3;
  unsigned rate=44100;tsf_set_output(font,TSF_STEREO_INTERLEAVED,rate,-12.0f);
  for(int c=0;c<16;c++)tsf_channel_set_presetnumber(font,c,0,0);
  double end=0;for(tml_message*m=song;m;m=m->next)if(m->time>end)end=m->time;
  unsigned frames=(unsigned)((end+6000.0)*rate/1000.0);
  FILE*out=fopen(argv[3],"wb");if(!out)return 4;
  fwrite("RIFF",1,4,out);u32(out,36+frames*8);fwrite("WAVEfmt ",1,8,out);u32(out,16);
  u16(out,3);u16(out,2);u32(out,rate);u32(out,rate*8);u16(out,8);u16(out,32);
  fwrite("data",1,4,out);u32(out,frames*8);
  tml_message*next=song;float block[512];double peak=0;
  for(unsigned frame=0;frame<frames;){
    double now=frame*1000.0/rate;
    while(next&&next->time<=now){
      if(next->type==TML_NOTE_ON&&next->velocity)tsf_channel_note_on(font,next->channel,next->key,next->velocity/127.0f);
      else if(next->type==TML_NOTE_OFF||next->type==TML_NOTE_ON)tsf_channel_note_off(font,next->channel,next->key);
      else if(next->type==TML_CONTROL_CHANGE)tsf_channel_midi_control(font,next->channel,next->control,next->control_value);
      next=next->next;
    }
    unsigned count=frames-frame;if(count>256)count=256;
    if(next){unsigned until=(unsigned)(next->time*rate/1000.0);if(until>frame&&until-frame<count)count=until-frame;}
    tsf_render_float(font,block,count,0);
    for(unsigned i=0;i<count*2;i++)if(fabs(block[i])>peak)peak=fabs(block[i]);
    fwrite(block,8,count,out);frame+=count;
  }
  fclose(out);tml_free(song);tsf_close(font);
  printf("{\"frames\":%u,\"seconds\":%.6f,\"float_peak\":%.8f,\"output\":\"float32 stereo; no integer clipping\"}\n",frames,frames/(double)rate,peak);
  return 0;
}
