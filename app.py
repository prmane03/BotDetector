from flask import Flask,request, url_for, redirect, render_template
import tweepy
import flask
import time
import datetime
import pickle
import numpy as np
import pandas as pd
import nltk
import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer 
from sklearn.feature_extraction.text import TfidfVectorizer
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import math, random
import string
import os
from nltk.stem.snowball import SnowballStemmer 
#the stemmer requires a language parameter 
snow_stemmer = SnowballStemmer(language='english') 
nltk.download('stopwords')
stopwords = nltk.corpus.stopwords.words('english')
ps = nltk.PorterStemmer()
gotData = [False,False,False]

auth = tweepy.OAuthHandler(os.environ['consumer_key'], os.environ['consumer_secret'])
auth.set_access_token(os.environ['access_token'],os.environ['access_secret'])
api = tweepy.API(auth)


app = Flask(__name__)

CONSUMER_TOKEN='fG2WoInquUXqZB5bG2BWvVSeb'
CONSUMER_SECRET='T2e6KSUoDs9g19FjpxKtRW0B9okz3SrAxYZd0vowymS6oNfkNv'
CALLBACK_URL = 'http://thebotdetector.herokuapp.com/verify'
session = dict()
db = dict() #you can save these values to a database

@app.route("/login")
def send_token():
    redirect_url= ''
    auth = tweepy.OAuthHandler(str(CONSUMER_TOKEN), 
        str(CONSUMER_SECRET), 
        str(CALLBACK_URL))
    try: 
        #get the request tokens
        redirect_url= auth.get_authorization_url()
        print(redirect_url)
        session['request_token']= (auth.request_token.key,
            auth.request_token.secret)
    except tweepy.TweepError:
        print ('Error! Failed to get request token')
    #this is twitter's url for authentication
    return flask.redirect(redirect_url)	

@app.route("/verify")
def get_verification():

	#get the verifier key from the request url
	verifier= request.args['oauth_verifier']

	auth = tweepy.OAuthHandler(CONSUMER_TOKEN, CONSUMER_SECRET)
	token = session['request_token']
	del session['request_token']

	auth.set_request_token(token[0], token[1])

	try:
		    auth.get_access_token(verifier)
	except tweepy.TweepError:
		    print ('Error! Failed to get access token.')

	#now you have access!
	api = tweepy.API(auth)

	#store in a db
	db['api']=api
	db['access_token_key']=auth.access_token.key
	db['access_token_secret']=auth.access_token.secret
	return flask.redirect(flask.url_for('start'))

@app.route("/start")
def start():
	#auth done, app logic can begin
	api = db['api']

	#example, print your latest status posts
	return flask.render_template('tweets.html', tweets=api.user_timeline())

def GetData(scrnm):
            ipvect=[]
            langvect=[0]*10
            user=api.get_user(scrnm)
            if(user):
                ipvect.append(user.default_profile)
                ipvect.append(user.default_profile_image)
                ipvect.append(user.favourites_count)
                ipvect.append(user.followers_count)
                ipvect.append(user.friends_count)
                ipvect.append(user.geo_enabled)
                ipvect.append(user.statuses_count)
                ipvect.append(user.verified) 
                account_age_days = (datetime.date.today()-user.created_at.date()).days
                # '''average_tweets_per_day'''        
                ipvect.append(user.statuses_count/account_age_days)                
                ipvect.append(account_age_days)                
                ipvect.append(len(user.description))                
                lang = ['en', 'es', 'pt', 'it', 'de', 'ja', 'fr',  'ar', 'af', 'id' ]
                language = user.lang
                if language in lang:
                    langvect[lang.index(language)] = 1
                ipvect += langvect
                col=[0,1,5,7]              
                for i in col:
                    ipvect[i]= int(ipvect[i])
                ipvect = np. reshape(ipvect, (1, len(ipvect)))
                gotData[0]=True
                return ipvect
            else :
                gotData[0]=False
                return 0;
                

def clean_text(txt):
    #remove punctuations 
    txt = "".join([c.lower() for c in txt if c not in string.punctuation])
    txt = ''.join(c for c in txt if not c.isdigit())
    tokens = re.split('\W+',txt)
    txt = [snow_stemmer.stem(word) for word in tokens if word not in stopwords]
    return txt
    
def GetTweets(scrnm):
    i=0
    tweet_text=[]
    for status in tweepy.Cursor(api.user_timeline,id=scrnm).items():
        i+=1
        tweet_text.append(status.text)
    #print(i,"##",status.text)
        if(i>200):
            break;
    #print("in get tweets")
    if(len(tweet_text)>30):
        # tweet_text = [tweet.text for tweet in tweets]
        #removing retweets
        for sent in tweet_text:
            if(sent.startswith("RT")):
                tweet_text.remove(sent)
            else:
                continue
        #print("no of tweets = ",len(tweet_text))
        if(len(tweet_text)>30):
            gotData[1]=True
            return tweet_text;
    else:
        gotData[1]=False
        return 0;

def GetTfidfVector(scrnm):
    tweet_text = GetTweets(scrnm);
    if(gotData[1]):
        #Tfidf = TfidfVectorizer(analyzer=CleanText)
        with open('vectorizer', 'rb') as file:
            Tfidf = pickle.load(file)
        x = Tfidf.transform(tweet_text)
        x = pd.DataFrame(x.toarray(), columns=Tfidf.get_feature_names())
        gotData[1]=True
        return x
    else:
        return 0;

def sentiment_scores(scrnm):
    tweet_text = GetTweets(scrnm);
    if(gotData[1]):
        SentScore ={}
        obj = SentimentIntensityAnalyzer()
        sentiment_dict = [obj.polarity_scores(text) for text in tweet_text]
        SentScore["neg"] = sum([tweet["neg"] for tweet in sentiment_dict])/len(sentiment_dict)
        SentScore["neu"] = sum([tweet["neu"] for tweet in sentiment_dict])/len(sentiment_dict)
        SentScore["pos"] = sum([tweet["pos"] for tweet in sentiment_dict])/len(sentiment_dict)
        #print("This is Sentiments : ",SentScore)
        return SentScore
    else:
        return 0;
    
ResultStatement =[
"Our model detects this account as Bot with probablity ",
"Our model detects this account as Real Account with probablity "
]

@app.route('/')
def checkpg():    
    data=None
    same_acc=None
    result=None
    return render_template("check.html",data=data,same_acc=same_acc,error=None,result=result)


@app.route('/about')
def about():
	return render_template("about.html")

    
 
@app.route('/search',methods=["POST","GET"])
def search():
	if request.method == 'POST':
		data=None
		usrnm = request.form.get("usrnm")
		try:
		      data = api.search_users(usrnm)
		      return render_template("search.html",data=data,error=None)
		except Exception as e:
		      #print("exception : ",e)
		      return render_template("search.html",data=data,error=e)
	else :
		return render_template("search.html",data=None,error=None)

@app.route('/contact',methods=["POST","GET"])
def contact():
    	if request.method =='POST':
    		name= request.form.get('name')
    		email=request.form.get('email')
    		receiver_email='prmane02@gmail.com'
    		sender_email='prmane03@gmail.com'
    		msg= request.form.get('message')
    		password = 'ptvvkxuxgztvfyll'
    		about = request.form.get("about")
    		message = MIMEMultipart("alternative")
    		message["Subject"] = "User trying to contact u. BotDetector"
    		message["From"] = email
    		message["To"] = receiver_email
    		html = """\
    		<html>
    		<body >
    		<b>Message About Bot Detector,</b><hr><b>User Details</b><p>Name :  """+name+"""<br>Email : """+email+"""<br>"""+name+""" has """+about+""" for you.<hr>"""+msg+"""
    		</p>
    		
    		</body>
    		</html>"""
    		# Turn these into plain/html MIMEText objects
    		#part1 = MIMEText(text, "plain")
    		part2 = MIMEText(html, "html")
    		# Add HTML/plain-text parts to MIMEMultipart message
    		# The email client will try to render the last part first
    		#message.attach(part1)
    		message.attach(part2)
    		# Create secure connection with server and send email
    		context = ssl.create_default_context()
    		with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
    			server.login(sender_email, password)
    			server.sendmail( sender_email, receiver_email, message.as_string())
    		return render_template("contact.html")
    	else : 
    		return render_template("contact.html")
    	
    	
@app.route('/check',methods=["POST","GET"])
def check(): 
    if request.method =='POST':
        data=None
        same_acc=None
        result=None;
        scrnm=request.form.get("scrnm")
        ipvect = [];
       
        
        try :
            user=api.get_user(scrnm)
            result=[None]*4
            #print("Got Screen Name : "+scrnm)
            same_acc= api.search_users(user.name)
            data={
            'user_name':user.name,
            'screen_name':scrnm,
            'description':user.description,
            'created_at':user.created_at.date(),
            'verified':user.verified,
            'profile_img':user.profile_image_url
            }
            
            features1 = GetData(scrnm)
            if(gotData[0]):
                with open('mod1x64.prm', 'rb') as file:
                    clf = pickle.load(file)
                #print("first Prediction")
                pred=clf.predict(features1)
                result[0]=ResultStatement[pred[0]]
                #print("0 stored")
                result[1]=clf.predict_proba(features1)
            
            features2 = GetTfidfVector(scrnm)
            if(gotData[1]):
                with open('mod2x64.prm', 'rb') as file:
                    clf2 = pickle.load(file)
                #print("second Prediction")   
                pred2 =clf2.predict(features2)
                d = clf2.decision_function(features2)[0]
                result[2]= 1 - (np.exp(d) / (1 + np.exp(d)))
                #print("1 stored")
                result[3] = sentiment_scores(scrnm)
            #print(result)
            #print("same_acc : ",same_acc[5])
            return render_template("check.html",data=data,same_acc=same_acc,error=None,result=result)
        except Exception as e:
            print("exceptuon : "+str(e))
            print(result)
            return render_template("check.html",data=data,same_acc=same_acc,error=e,result=result)
        


if __name__ == '__main__':
    app.debug = True
    app.run()
